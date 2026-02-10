"""CNAB 240/400 Parser for Brazilian bank return files.

Parses FEBRABAN CNAB 240 and CNAB 400 formats used by Brazilian banks
for payment return files (arquivo de retorno).

References:
- FEBRABAN CNAB 240: Layout padrão de pagamentos
- FEBRABAN CNAB 400: Layout padrão de cobrança
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum, unique
from typing import Any

from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.revenue_cycle.collection.enums import CNABFormat
from healthcare_platform.revenue_cycle.collection.exceptions import CNABParsingError

logger = get_logger(__name__)


@unique
class CNABRecordType(StrEnum):
    HEADER_ARQUIVO = "0"
    HEADER_LOTE = "1"
    DETALHE = "3"
    TRAILER_LOTE = "5"
    TRAILER_ARQUIVO = "9"


@unique
class CNABSegment(StrEnum):
    T = "T"  # Título (payment identification)
    U = "U"  # Complemento (payment values)
    J = "J"  # Pagamento de títulos
    A = "A"  # Pagamento (crédito em conta)


@unique
class CNABOccurrence(StrEnum):
    LIQUIDACAO_NORMAL = "06"
    LIQUIDACAO_PARCIAL = "17"
    ENTRADA_CONFIRMADA = "02"
    ENTRADA_REJEITADA = "03"
    BAIXA = "09"
    PROTESTADO = "23"
    SUSTACAO_PROTESTO = "24"


@dataclass(frozen=True, slots=True)
class CNABFileHeader:
    """Header record of a CNAB file."""
    bank_code: str
    bank_name: str
    company_name: str
    company_cnpj: str
    file_date: date
    file_sequence: int
    cnab_format: CNABFormat
    layout_version: str = ""


@dataclass(frozen=True, slots=True)
class CNABPaymentRecord:
    """A single payment record parsed from CNAB file."""
    nosso_numero: str
    seu_numero: str
    payment_date: date | None
    credit_date: date | None
    gross_amount: Decimal
    discount_amount: Decimal
    interest_amount: Decimal
    penalty_amount: Decimal
    net_amount: Decimal
    occurrence_code: str
    occurrence_description: str
    payer_name: str
    payer_document: str
    bank_code: str
    agency: str
    account: str
    line_number: int
    raw_line: str = ""


@dataclass
class CNABFileResult:
    """Result of parsing a complete CNAB file."""
    header: CNABFileHeader
    payments: list[CNABPaymentRecord] = field(default_factory=list)
    total_records: int = 0
    total_amount: Decimal = Decimal("0.00")
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CNAB 240 Parser
# ---------------------------------------------------------------------------

_CNAB240_OCCURRENCE_MAP: dict[str, str] = {
    "00": "Crédito ou débito efetivado",
    "01": "Insuficiência de fundos",
    "02": "Crédito ou débito cancelado pelo pagador",
    "03": "Débito autorizado pela agência",
    "AA": "Controle inválido",
    "AB": "Tipo de operação inválido",
    "AC": "Tipo de serviço inválido",
    "BD": "Banco destinatário inválido",
}


def _parse_cnab240_date(raw: str) -> date | None:
    """Parse date from CNAB 240 format (DDMMAAAA)."""
    if not raw or raw.strip() == "" or raw == "00000000":
        return None
    try:
        return datetime.strptime(raw.strip(), "%d%m%Y").date()
    except ValueError:
        return None


def _parse_cnab240_amount(raw: str) -> Decimal:
    """Parse amount from CNAB 240 (last 2 digits are cents)."""
    raw = raw.strip()
    if not raw or not raw.isdigit():
        return Decimal("0.00")
    return Decimal(raw) / Decimal("100")


def parse_cnab240(content: str) -> CNABFileResult:
    """Parse a CNAB 240 return file.

    Args:
        content: Raw file content (one record per line, 240 chars each).

    Returns:
        CNABFileResult with header and payment records.

    Raises:
        CNABParsingError: If file structure is invalid.
    """
    lines = content.splitlines()
    if not lines:
        raise CNABParsingError(_("Arquivo CNAB 240 vazio"))

    # Validate line length
    first_line = lines[0]
    if len(first_line) < 240:
        raise CNABParsingError(
            _("Linha do arquivo CNAB 240 deve ter 240 caracteres, encontrado: {n}").format(
                n=len(first_line)
            )
        )

    # Parse header (record type 0)
    header_line = lines[0]
    if header_line[7] != "0":
        raise CNABParsingError(_("Registro de header de arquivo inválido"))

    header = CNABFileHeader(
        bank_code=header_line[0:3].strip(),
        bank_name=header_line[102:132].strip(),
        company_name=header_line[72:102].strip(),
        company_cnpj=header_line[18:32].strip(),
        file_date=_parse_cnab240_date(header_line[143:151]) or date.today(),
        file_sequence=int(header_line[157:163].strip() or "0"),
        cnab_format=CNABFormat.CNAB_240,
        layout_version=header_line[163:166].strip(),
    )

    payments: list[CNABPaymentRecord] = []
    errors: list[str] = []
    total_amount = Decimal("0.00")

    # Parse detail records (segment T + U pairs)
    segment_t: dict[str, Any] | None = None

    for line_num, line in enumerate(lines[1:], start=2):
        if len(line) < 240:
            errors.append(f"Linha {line_num}: comprimento inválido ({len(line)})")
            continue

        record_type = line[7]
        if record_type != "3":
            continue  # Skip non-detail records

        segment = line[13]

        if segment == "T":
            # Segment T: Payment identification
            segment_t = {
                "nosso_numero": line[37:57].strip(),
                "seu_numero": line[58:73].strip(),
                "payment_date": _parse_cnab240_date(line[73:81]),
                "gross_amount": _parse_cnab240_amount(line[81:96]),
                "occurrence_code": line[15:17],
                "bank_code": line[0:3].strip(),
                "agency": line[17:22].strip(),
                "account": line[22:35].strip(),
                "payer_name": line[148:188].strip(),
                "payer_document": line[133:148].strip(),
                "line_number": line_num,
            }

        elif segment == "U" and segment_t is not None:
            # Segment U: Payment values (complement to T)
            credit_date = _parse_cnab240_date(line[145:153])
            discount = _parse_cnab240_amount(line[32:47])
            interest = _parse_cnab240_amount(line[17:32])
            penalty = _parse_cnab240_amount(line[47:62])
            net_amount = _parse_cnab240_amount(line[77:92])

            occ = segment_t["occurrence_code"]
            occ_desc = _CNAB240_OCCURRENCE_MAP.get(occ, f"Código {occ}")

            record = CNABPaymentRecord(
                nosso_numero=segment_t["nosso_numero"],
                seu_numero=segment_t["seu_numero"],
                payment_date=segment_t["payment_date"],
                credit_date=credit_date,
                gross_amount=segment_t["gross_amount"],
                discount_amount=discount,
                interest_amount=interest,
                penalty_amount=penalty,
                net_amount=net_amount,
                occurrence_code=occ,
                occurrence_description=occ_desc,
                payer_name=segment_t["payer_name"],
                payer_document=segment_t["payer_document"],
                bank_code=segment_t["bank_code"],
                agency=segment_t["agency"],
                account=segment_t["account"],
                line_number=segment_t["line_number"],
            )
            payments.append(record)
            total_amount += net_amount
            segment_t = None

    logger.info(
        "cnab240_parsed",
        bank_code=header.bank_code,
        payment_count=len(payments),
        error_count=len(errors),
    )

    return CNABFileResult(
        header=header,
        payments=payments,
        total_records=len(payments),
        total_amount=total_amount,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CNAB 400 Parser
# ---------------------------------------------------------------------------

_CNAB400_OCCURRENCE_MAP: dict[str, str] = {
    "02": "Entrada confirmada",
    "03": "Entrada rejeitada",
    "06": "Liquidação normal",
    "09": "Baixa",
    "10": "Baixa por ter sido pago",
    "17": "Liquidação parcial",
    "23": "Encaminhado a protesto",
    "24": "Sustação de protesto",
    "25": "Protesto sustado por ordem judicial",
    "28": "Tarifa mensal referente a entradas",
}


def _parse_cnab400_date(raw: str) -> date | None:
    """Parse date from CNAB 400 format (DDMMAA or DDMMAAAA)."""
    raw = raw.strip()
    if not raw or raw in ("000000", "00000000"):
        return None
    try:
        if len(raw) == 6:
            d = datetime.strptime(raw, "%d%m%y")
        else:
            d = datetime.strptime(raw, "%d%m%Y")
        return d.date()
    except ValueError:
        return None


def _parse_cnab400_amount(raw: str) -> Decimal:
    """Parse amount from CNAB 400 (last 2 digits are cents)."""
    raw = raw.strip()
    if not raw or not raw.isdigit():
        return Decimal("0.00")
    return Decimal(raw) / Decimal("100")


def parse_cnab400(content: str) -> CNABFileResult:
    """Parse a CNAB 400 return file.

    Args:
        content: Raw file content (one record per line, 400 chars each).

    Returns:
        CNABFileResult with header and payment records.

    Raises:
        CNABParsingError: If file structure is invalid.
    """
    lines = content.splitlines()
    if not lines:
        raise CNABParsingError(_("Arquivo CNAB 400 vazio"))

    first_line = lines[0]
    if len(first_line) < 400:
        raise CNABParsingError(
            _("Linha do arquivo CNAB 400 deve ter 400 caracteres, encontrado: {n}").format(
                n=len(first_line)
            )
        )

    # Parse header (record type 0)
    header_line = lines[0]
    if header_line[0] != "0":
        raise CNABParsingError(_("Registro de header de arquivo inválido"))

    header = CNABFileHeader(
        bank_code=header_line[76:79].strip(),
        bank_name=header_line[79:94].strip(),
        company_name=header_line[46:76].strip(),
        company_cnpj=header_line[2:16].strip(),
        file_date=_parse_cnab400_date(header_line[94:100]) or date.today(),
        file_sequence=int(header_line[108:113].strip() or "0"),
        cnab_format=CNABFormat.CNAB_400,
    )

    payments: list[CNABPaymentRecord] = []
    errors: list[str] = []
    total_amount = Decimal("0.00")

    for line_num, line in enumerate(lines[1:], start=2):
        if len(line) < 400:
            errors.append(f"Linha {line_num}: comprimento inválido ({len(line)})")
            continue

        record_type = line[0]
        if record_type != "1":
            continue  # Only type 1 = detail

        occurrence = line[108:110]
        occ_desc = _CNAB400_OCCURRENCE_MAP.get(occurrence, f"Código {occurrence}")

        gross_amount = _parse_cnab400_amount(line[152:165])
        discount = _parse_cnab400_amount(line[240:253])
        interest = _parse_cnab400_amount(line[266:279])
        penalty = Decimal("0.00")  # CNAB 400 varies by bank
        net_amount = _parse_cnab400_amount(line[253:266])

        record = CNABPaymentRecord(
            nosso_numero=line[62:73].strip(),
            seu_numero=line[116:126].strip(),
            payment_date=_parse_cnab400_date(line[295:301]),
            credit_date=_parse_cnab400_date(line[175:181]),
            gross_amount=gross_amount,
            discount_amount=discount,
            interest_amount=interest,
            penalty_amount=penalty,
            net_amount=net_amount,
            occurrence_code=occurrence,
            occurrence_description=occ_desc,
            payer_name=line[324:354].strip(),
            payer_document=line[3:17].strip(),
            bank_code=header.bank_code,
            agency=line[17:21].strip(),
            account=line[21:28].strip(),
            line_number=line_num,
        )
        payments.append(record)
        total_amount += net_amount

    logger.info(
        "cnab400_parsed",
        bank_code=header.bank_code,
        payment_count=len(payments),
        error_count=len(errors),
    )

    return CNABFileResult(
        header=header,
        payments=payments,
        total_records=len(payments),
        total_amount=total_amount,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Auto-detect and parse
# ---------------------------------------------------------------------------


def parse_cnab(content: str) -> CNABFileResult:
    """Auto-detect CNAB format (240 or 400) and parse.

    Detects format by line length of the first line.

    Args:
        content: Raw CNAB file content.

    Returns:
        CNABFileResult.

    Raises:
        CNABParsingError: If format cannot be detected.
    """
    lines = content.splitlines()
    if not lines:
        raise CNABParsingError(_("Arquivo CNAB vazio"))

    first_line_len = len(lines[0])

    if first_line_len >= 400:
        return parse_cnab400(content)
    elif first_line_len >= 240:
        return parse_cnab240(content)
    else:
        raise CNABParsingError(
            _("Formato CNAB não reconhecido (comprimento da linha: {n})").format(
                n=first_line_len
            )
        )
