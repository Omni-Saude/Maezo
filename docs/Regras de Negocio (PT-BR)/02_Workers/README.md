# Workers Documentation Index

## 📁 Structure

This directory contains business rule documentation for all External Task Workers in the Revenue Cycle Management system.

---

## 📋 Workers Inventory

### ✅ Infrastructure (2 files)
- **RN-BaseWorker.md** - Abstract base class with Template Method, Circuit Breaker, Retry, Metrics
- **RN-ExternalTaskClientConfig.md** - Spring configuration for 10 workers across 3 categories

### ⚠️ IoT Workers (2 files - MOCK Mode)
- **RN-RFIDCaptureWorker.md** - RFID tag capture (HUMAN-006 blocked)
- **RN-WeightSensorWorker.md** - Weight sensor readings (HUMAN-006 blocked)

### ✅ Notification Workers (3 files - PRODUCTION)
- **RN-GenericNotificationWorker.md** - Multi-channel notifications (stub)
- **RN-NotificacaoPacienteWorker.md** - WhatsApp patient notifications
- **RN-NotificationServiceWorker.md** - SMS/Email/Push/Alert service

### ✅/⚠️ RPA Workers (6 files - Mixed Status)
- **RN-CNABParserWorker.md** - CNAB 240/400/750 parser ✅ FUNCTIONAL
- **RN-PortalScrapingWorker.md** - Insurance portal scraping ⚠️ MOCK (HUMANA-008)
- **RN-PortalSubmitWorker.md** - Appeal submission ⚠️ MOCK (HUMANA-008)
- **RN-PortalUploadWorker.md** - TISS file upload ⚠️ MOCK (HUMANA-008)
- **RN-ReportGenerationWorker.md** - PDF/Excel/CSV generation ✅ FUNCTIONAL
- **RN-StatusCheckWorker.md** - Portal status polling ⚠️ MOCK (HUMANA-008)

**Total**: 13 Worker Documentation Files

---

## 🎯 Quick Reference

### Worker Topics (BPMN)
```
Notifications:
  - notificacao-paciente        → NotificacaoPacienteWorker
  - notification-service        → NotificationServiceWorker

IoT (MOCK):
  - iot-rfid-capture           → RFIDCaptureWorker
  - iot-weight-sensor          → WeightSensorWorker

RPA:
  - rpa-cnab-parser            → CNABParserWorker ✅
  - rpa-portal-scraping        → PortalScrapingWorker ⚠️
  - rpa-portal-submit          → PortalSubmitWorker ⚠️
  - rpa-portal-upload          → PortalUploadWorker ⚠️
  - rpa-report-generation      → ReportGenerationWorker ✅
  - rpa-status-check           → StatusCheckWorker ⚠️
```

### Implementation Blockers

| Blocker | Affected Workers | Count |
|---------|------------------|-------|
| **HUMAN-006** (IoT Access) | RFID, Weight Sensor | 2 |
| **HUMANA-008** (Portal Credentials) | Portal Scraping, Submit, Upload, Status Check | 4 |

---

## 📊 Status Summary

- ✅ **Production Ready**: 5 workers (NotificacaoPaciente, NotificationService, CNABParser, ReportGeneration, GenericNotification)
- ⚠️ **Mock Mode**: 6 workers (2 IoT + 4 RPA awaiting credentials)
- 🏗️ **Stub**: 1 worker (GenericNotification - basic JavaDelegate)

**Implementation Rate**: 50% functional (5/10 workers)

---

## 🔧 All Workers Extend BaseWorker

Every worker follows the pattern:

```java
@Component
public class XWorker extends BaseWorker {
    
    public XWorker(MeterRegistry meterRegistry) {
        super(meterRegistry, "topic-name");
    }
    
    @Override
    protected Map<String, Object> processTask(
            ExternalTask task,
            ExternalTaskService service) throws Exception {
        // Business logic
        return outputVariables;
    }
}
```

Benefits:
- ✅ Circuit Breaker (Resilience4j)
- ✅ Exponential Backoff Retry
- ✅ Automatic Metrics (Micrometer)
- ✅ BPMN Error Handling
- ✅ Variable Helper Methods

---

## 📚 Documentation Template

Each worker documentation includes:

1. **Metadata** - ID, Category, Version, File Location
2. **Overview** - Purpose, Responsibilities
3. **BPMN Integration** - Topic, Input/Output Variables
4. **Business Rules** - Processing Logic, Validation
5. **Error Handling** - Error Codes, Retry Strategy
6. **Metrics** - Counters, Timers, Tags
7. **Examples** - Code Samples, Usage Patterns
8. **Status** - Production/Mock/TODO indicators

---

