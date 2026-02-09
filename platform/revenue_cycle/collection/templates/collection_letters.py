"""Portuguese collection letter templates for Brazilian healthcare.

All letters follow Brazilian legal requirements and are written in Portuguese.
Templates use string.Template for safe variable substitution.
"""
from __future__ import annotations

from string import Template

# ---------------------------------------------------------------------------
# First Notice (Aviso Amigável)
# ---------------------------------------------------------------------------

FIRST_NOTICE = Template("""
Prezado(a) $payer_name,

Ref.: Cobrança de Serviços Hospitalares
Fatura Nº: $invoice_number
Valor: R$$ $amount
Vencimento: $due_date

Informamos que até a presente data não identificamos o pagamento referente
à fatura acima especificada, relativa aos serviços prestados ao(à) paciente
atendido(a) em nosso hospital.

Solicitamos a gentileza de providenciar o pagamento no prazo de 15 (quinze)
dias úteis a partir do recebimento desta notificação.

Caso o pagamento já tenha sido efetuado, por favor desconsidere este aviso
e envie o comprovante para nosso departamento financeiro.

Atenciosamente,
$hospital_name
Departamento de Contas a Receber
$contact_phone
$contact_email
""".strip())

# ---------------------------------------------------------------------------
# Second Notice (Segunda Notificação)
# ---------------------------------------------------------------------------

SECOND_NOTICE = Template("""
Prezado(a) $payer_name,

Ref.: SEGUNDA NOTIFICAÇÃO - Cobrança de Serviços Hospitalares
Fatura Nº: $invoice_number
Valor Original: R$$ $original_amount
Juros e Multa: R$$ $penalty_amount
Valor Total Atualizado: R$$ $total_amount
Vencimento Original: $due_date
Dias em Atraso: $days_overdue

Conforme comunicação anterior, informamos que o débito referente à fatura
acima permanece em aberto.

De acordo com o Código Civil Brasileiro (Lei 10.406/2002), incidem sobre
o valor em atraso:
- Multa de 2% sobre o valor principal
- Juros de mora de 1% ao mês (pro rata die)
- Correção monetária pelo INPC

Solicitamos o pagamento imediato para evitar medidas adicionais de cobrança.

Para negociação de parcelamento, entre em contato conosco.

Atenciosamente,
$hospital_name
Departamento de Contas a Receber
$contact_phone
$contact_email
""".strip())

# ---------------------------------------------------------------------------
# Final Notice (Notificação Final / Pré-Jurídica)
# ---------------------------------------------------------------------------

FINAL_NOTICE = Template("""
Prezado(a) $payer_name,

Ref.: NOTIFICAÇÃO FINAL - AVISO PRÉ-JURÍDICO
Fatura Nº: $invoice_number
Valor Total Atualizado: R$$ $total_amount
Dias em Atraso: $days_overdue

Apesar de nossas comunicações anteriores, o débito acima permanece pendente.

Esta é a última notificação antes do encaminhamento ao departamento jurídico
para as providências cabíveis, incluindo:

1. Protesto do título em cartório
2. Inscrição nos órgãos de proteção ao crédito (SPC/Serasa)
3. Ação judicial de cobrança

Concedemos o prazo final e improrrogável de 5 (cinco) dias úteis para
regularização do débito.

Para quitação ou negociação, entre em contato urgente:
Telefone: $contact_phone
E-mail: $contact_email

$hospital_name
Departamento Jurídico / Contas a Receber
""".strip())

# ---------------------------------------------------------------------------
# WhatsApp Reminder Templates
# ---------------------------------------------------------------------------

WHATSAPP_FIRST_REMINDER = Template(
    "Olá! Informamos que a fatura Nº $invoice_number no valor de "
    "R$$ $amount com vencimento em $due_date encontra-se pendente. "
    "Por favor, providencie o pagamento ou entre em contato: $contact_phone. "
    "Obrigado, $hospital_name."
)

WHATSAPP_OVERDUE_REMINDER = Template(
    "Atenção: A fatura Nº $invoice_number está com $days_overdue dias de atraso. "
    "Valor atualizado: R$$ $total_amount. "
    "Regularize para evitar juros adicionais. "
    "Contato: $contact_phone. $hospital_name."
)

WHATSAPP_PAYMENT_CONFIRMED = Template(
    "Confirmamos o recebimento do pagamento referente à fatura "
    "Nº $invoice_number no valor de R$$ $amount. "
    "Agradecemos pela pontualidade. $hospital_name."
)

# ---------------------------------------------------------------------------
# Helper to render
# ---------------------------------------------------------------------------

LETTER_TEMPLATES = {
    "first_notice": FIRST_NOTICE,
    "second_notice": SECOND_NOTICE,
    "final_notice": FINAL_NOTICE,
}

WHATSAPP_TEMPLATES = {
    "first_reminder": WHATSAPP_FIRST_REMINDER,
    "overdue_reminder": WHATSAPP_OVERDUE_REMINDER,
    "payment_confirmed": WHATSAPP_PAYMENT_CONFIRMED,
}


def render_letter(template_name: str, **kwargs: str) -> str:
    """Render a collection letter template with safe substitution."""
    tpl = LETTER_TEMPLATES.get(template_name)
    if tpl is None:
        raise ValueError(f"Template desconhecido: {template_name}")
    return tpl.safe_substitute(**kwargs)


def render_whatsapp(template_name: str, **kwargs: str) -> str:
    """Render a WhatsApp message template with safe substitution."""
    tpl = WHATSAPP_TEMPLATES.get(template_name)
    if tpl is None:
        raise ValueError(f"Template WhatsApp desconhecido: {template_name}")
    return tpl.safe_substitute(**kwargs)
