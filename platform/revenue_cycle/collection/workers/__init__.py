"""External task workers for Revenue Collection subprocess."""
from __future__ import annotations

# A. Payment Reception (8)
from platform.revenue_cycle.collection.workers.receive_payment_notification_worker import ReceivePaymentNotificationWorker
from platform.revenue_cycle.collection.workers.parse_payment_file_worker import ParsePaymentFileWorker
from platform.revenue_cycle.collection.workers.validate_payment_data_worker import ValidatePaymentDataWorker
from platform.revenue_cycle.collection.workers.convert_currency_worker import ConvertCurrencyWorker
from platform.revenue_cycle.collection.workers.calculate_net_payment_worker import CalculateNetPaymentWorker
from platform.revenue_cycle.collection.workers.detect_duplicate_payment_worker import DetectDuplicatePaymentWorker
from platform.revenue_cycle.collection.workers.classify_payment_type_worker import ClassifyPaymentTypeWorker
from platform.revenue_cycle.collection.workers.persist_payment_worker import PersistPaymentWorker

# B. Payment Allocation (12)
from platform.revenue_cycle.collection.workers.auto_matching_worker import AutoMatchingWorker
from platform.revenue_cycle.collection.workers.match_by_protocol_worker import MatchByProtocolWorker
from platform.revenue_cycle.collection.workers.match_by_invoice_worker import MatchByInvoiceWorker
from platform.revenue_cycle.collection.workers.match_by_patient_worker import MatchByPatientWorker
from platform.revenue_cycle.collection.workers.partial_allocation_worker import PartialAllocationWorker
from platform.revenue_cycle.collection.workers.handle_overpayment_worker import HandleOverpaymentWorker
from platform.revenue_cycle.collection.workers.handle_underpayment_worker import HandleUnderpaymentWorker
from platform.revenue_cycle.collection.workers.apply_contractual_adjustments_worker import ApplyContractualAdjustmentsWorker
from platform.revenue_cycle.collection.workers.calculate_variance_worker import CalculateVarianceWorker
from platform.revenue_cycle.collection.workers.flag_discrepancies_worker import FlagDiscrepanciesWorker
from platform.revenue_cycle.collection.workers.escalate_unmatched_worker import EscalateUnmatchedWorker
from platform.revenue_cycle.collection.workers.finalize_allocation_worker import FinalizeAllocationWorker

# C. Reconciliation (10)
from platform.revenue_cycle.collection.workers.reconcile_daily_worker import ReconcileDailyWorker
from platform.revenue_cycle.collection.workers.reconcile_weekly_worker import ReconcileWeeklyWorker
from platform.revenue_cycle.collection.workers.reconcile_monthly_worker import ReconcileMonthlyWorker
from platform.revenue_cycle.collection.workers.generate_aging_report_worker import GenerateAgingReportWorker
from platform.revenue_cycle.collection.workers.calculate_dso_worker import CalculateDSOWorker
from platform.revenue_cycle.collection.workers.identify_slow_payers_worker import IdentifySlowPayersWorker
from platform.revenue_cycle.collection.workers.predict_collection_date_worker import PredictCollectionDateWorker
from platform.revenue_cycle.collection.workers.update_forecasts_worker import UpdateForecastsWorker
from platform.revenue_cycle.collection.workers.export_to_erp_worker import ExportToERPWorker
from platform.revenue_cycle.collection.workers.archive_reconciliation_worker import ArchiveReconciliationWorker

# D. Collections & Follow-up (10)
from platform.revenue_cycle.collection.workers.identify_overdue_worker import IdentifyOverdueWorker
from platform.revenue_cycle.collection.workers.calculate_aging_bucket_worker import CalculateAgingBucketWorker
from platform.revenue_cycle.collection.workers.prioritize_collection_worker import PrioritizeCollectionWorker
from platform.revenue_cycle.collection.workers.generate_collection_letter_worker import GenerateCollectionLetterWorker
from platform.revenue_cycle.collection.workers.send_whatsapp_reminder_worker import SendWhatsappReminderWorker
from platform.revenue_cycle.collection.workers.schedule_collection_call_worker import ScheduleCollectionCallWorker
from platform.revenue_cycle.collection.workers.negotiate_payment_plan_worker import NegotiatePaymentPlanWorker
from platform.revenue_cycle.collection.workers.apply_penalties_worker import ApplyPenaltiesWorker
from platform.revenue_cycle.collection.workers.escalate_to_legal_worker import EscalateToLegalWorker
from platform.revenue_cycle.collection.workers.write_off_bad_debt_worker import WriteOffBadDebtWorker

# E. Reporting & Analytics (8)
from platform.revenue_cycle.collection.workers.calculate_collection_rate_worker import CalculateCollectionRateWorker
from platform.revenue_cycle.collection.workers.calculate_revenue_cycle_time_worker import CalculateRevenueCycleTimeWorker
from platform.revenue_cycle.collection.workers.analyze_payer_performance_worker import AnalyzePayerPerformanceWorker
from platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker import DetectRevenueLeakageWorker
from platform.revenue_cycle.collection.workers.generate_executive_dashboard_worker import GenerateExecutiveDashboardWorker
from platform.revenue_cycle.collection.workers.send_daily_summary_worker import SendDailySummaryWorker
from platform.revenue_cycle.collection.workers.update_bi_datawarehouse_worker import UpdateBIDatawarehouseWorker
from platform.revenue_cycle.collection.workers.alert_anomalies_worker import AlertAnomaliesWorker

__all__ = [
    # A. Payment Reception
    "ReceivePaymentNotificationWorker",
    "ParsePaymentFileWorker",
    "ValidatePaymentDataWorker",
    "ConvertCurrencyWorker",
    "CalculateNetPaymentWorker",
    "DetectDuplicatePaymentWorker",
    "ClassifyPaymentTypeWorker",
    "PersistPaymentWorker",
    # B. Payment Allocation
    "AutoMatchingWorker",
    "MatchByProtocolWorker",
    "MatchByInvoiceWorker",
    "MatchByPatientWorker",
    "PartialAllocationWorker",
    "HandleOverpaymentWorker",
    "HandleUnderpaymentWorker",
    "ApplyContractualAdjustmentsWorker",
    "CalculateVarianceWorker",
    "FlagDiscrepanciesWorker",
    "EscalateUnmatchedWorker",
    "FinalizeAllocationWorker",
    # C. Reconciliation
    "ReconcileDailyWorker",
    "ReconcileWeeklyWorker",
    "ReconcileMonthlyWorker",
    "GenerateAgingReportWorker",
    "CalculateDSOWorker",
    "IdentifySlowPayersWorker",
    "PredictCollectionDateWorker",
    "UpdateForecastsWorker",
    "ExportToERPWorker",
    "ArchiveReconciliationWorker",
    # D. Collections & Follow-up
    "IdentifyOverdueWorker",
    "CalculateAgingBucketWorker",
    "PrioritizeCollectionWorker",
    "GenerateCollectionLetterWorker",
    "SendWhatsappReminderWorker",
    "ScheduleCollectionCallWorker",
    "NegotiatePaymentPlanWorker",
    "ApplyPenaltiesWorker",
    "EscalateToLegalWorker",
    "WriteOffBadDebtWorker",
    # E. Reporting & Analytics
    "CalculateCollectionRateWorker",
    "CalculateRevenueCycleTimeWorker",
    "AnalyzePayerPerformanceWorker",
    "DetectRevenueLeakageWorker",
    "GenerateExecutiveDashboardWorker",
    "SendDailySummaryWorker",
    "UpdateBIDatawarehouseWorker",
    "AlertAnomaliesWorker",
]
