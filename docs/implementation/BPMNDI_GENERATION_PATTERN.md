# BPMNDI Generation Pattern - Lessons Learned

```yaml
pilot_date: 2026-02-14
pilot_file: SP-RC-001_Scheduling_Registration.bpmn
status: SUCCESS
trajectory_ids:
  - traj-1771098268614  # Pilot completion
  - traj-1771098275776  # Pattern documentation
```

---

## Overview

This document captures the validated pattern for adding BPMNDI (visual representation) to BPMN files that have semantic structure but lack diagram metadata.

## Pilot Results

| Metric | Before | After |
|--------|--------|-------|
| Lines | 127 | 286 |
| Shapes | 0 | 12 |
| Edges | 0 | 10 |
| XML Valid | ✅ | ✅ |
| Lines Added | - | 159 (BPMNDI section) |

---

## Pattern Specification

### 1. ID Naming Convention

```yaml
shapes:
  pattern: "Shape_${elementId}"
  examples:
    - "Shape_start_scheduling"
    - "Shape_task_verify_insurance"
    - "Shape_gateway_eligibility"
    
edges:
  pattern: "Edge_${flowId}"
  examples:
    - "Edge_flow_to_verify_insurance"
    - "Edge_flow_eligible_yes"
```

### 2. Layout Coordinates

```yaml
horizontal_flow:
  start_x: 152
  task_spacing: 160  # x increment per element
  task_width: 100
  task_height: 80

vertical_lanes:
  main_flow_y: 80      # Happy path
  error_path_y: 280    # Error/timer exception paths
  escalation_y: 400    # Further escalation

event_dimensions:
  start_end_event:
    width: 36
    height: 36
  boundary_event:
    width: 36
    height: 36

gateway_dimensions:
  width: 50
  height: 50
  marker_visible: true  # For exclusive gateways
```

### 3. Boundary Event Positioning

Boundary events attach to the bottom edge of their parent task:

```yaml
boundary_event_offset:
  timer_boundary:
    x_offset: 12   # From parent left edge
    y_offset: 62   # From parent top (places at bottom)
  error_boundary:
    x_offset: 72   # From parent left edge (right side)
    y_offset: 62   # Same vertical position
```

**Example:**
```xml
<!-- Parent task at x=240, y=80, width=100, height=80 -->
<bpmndi:BPMNShape id="Shape_task_verify_insurance" bpmnElement="task_verify_insurance">
  <dc:Bounds x="240" y="80" width="100" height="80"/>
</bpmndi:BPMNShape>

<!-- Timer boundary at bottom-left: x=240+12=252, y=80+62=142 -->
<bpmndi:BPMNShape id="Shape_timer_insurance_sla" bpmnElement="timer_insurance_sla">
  <dc:Bounds x="252" y="142" width="36" height="36"/>
</bpmndi:BPMNShape>

<!-- Error boundary at bottom-right: x=240+72=312, y=80+62=142 -->
<bpmndi:BPMNShape id="Shape_error_insurance_verification" bpmnElement="error_insurance_verification">
  <dc:Bounds x="312" y="142" width="36" height="36"/>
</bpmndi:BPMNShape>
```

### 4. Label Positioning

```yaml
labels:
  start_end_events:
    y_offset: 43  # Below event circle
    centered: true
    
  gateways:
    y_offset: -30  # Above gateway diamond
    centered: true
    
  tasks:
    # Labels are inside task boxes, no separate BPMNLabel needed
    
  edges_with_conditions:
    # Position label near source waypoint
    y_offset: -18  # Above the edge line
```

### 5. Edge Waypoints

```yaml
straight_horizontal:
  waypoints: 2
  pattern: |
    <di:waypoint x="${source.x + source.width}" y="${source.centerY}"/>
    <di:waypoint x="${target.x}" y="${target.centerY}"/>

vertical_turn:
  waypoints: 3  # or more for complex routing
  pattern: |
    <di:waypoint x="${source.centerX}" y="${source.y + source.height}"/>
    <di:waypoint x="${source.centerX}" y="${midpoint_y}"/>
    <di:waypoint x="${target.x}" y="${midpoint_y}"/>
```

---

## BPMNDI Template Structure

```xml
<bpmndi:BPMNDiagram id="BPMNDiagram_${processId}">
  <bpmndi:BPMNPlane id="BPMNPlane_${processId}" bpmnElement="${processId}">

    <!-- Start Event -->
    <bpmndi:BPMNShape id="Shape_${startEventId}" bpmnElement="${startEventId}">
      <dc:Bounds x="152" y="102" width="36" height="36"/>
      <bpmndi:BPMNLabel>
        <dc:Bounds x="130" y="145" width="80" height="27"/>
      </bpmndi:BPMNLabel>
    </bpmndi:BPMNShape>

    <!-- Service/User Tasks -->
    <bpmndi:BPMNShape id="Shape_${taskId}" bpmnElement="${taskId}">
      <dc:Bounds x="${x}" y="${y}" width="100" height="80"/>
    </bpmndi:BPMNShape>

    <!-- Boundary Events (attached to tasks) -->
    <bpmndi:BPMNShape id="Shape_${boundaryEventId}" bpmnElement="${boundaryEventId}">
      <dc:Bounds x="${parentX + offset}" y="${parentY + 62}" width="36" height="36"/>
      <bpmndi:BPMNLabel>
        <dc:Bounds x="${labelX}" y="${labelY}" width="40" height="14"/>
      </bpmndi:BPMNLabel>
    </bpmndi:BPMNShape>

    <!-- Gateways -->
    <bpmndi:BPMNShape id="Shape_${gatewayId}" bpmnElement="${gatewayId}" isMarkerVisible="true">
      <dc:Bounds x="${x}" y="${y}" width="50" height="50"/>
      <bpmndi:BPMNLabel>
        <dc:Bounds x="${x+5}" y="${y-30}" width="40" height="14"/>
      </bpmndi:BPMNLabel>
    </bpmndi:BPMNShape>

    <!-- End Events -->
    <bpmndi:BPMNShape id="Shape_${endEventId}" bpmnElement="${endEventId}">
      <dc:Bounds x="${x}" y="${y}" width="36" height="36"/>
      <bpmndi:BPMNLabel>
        <dc:Bounds x="${x-10}" y="${y+43}" width="80" height="27"/>
      </bpmndi:BPMNLabel>
    </bpmndi:BPMNShape>

    <!-- Sequence Flow Edges -->
    <bpmndi:BPMNEdge id="Edge_${flowId}" bpmnElement="${flowId}">
      <di:waypoint x="${sourceX}" y="${sourceY}"/>
      <di:waypoint x="${targetX}" y="${targetY}"/>
      <!-- Optional label for conditional flows -->
      <bpmndi:BPMNLabel>
        <dc:Bounds x="${labelX}" y="${labelY}" width="20" height="14"/>
      </bpmndi:BPMNLabel>
    </bpmndi:BPMNEdge>

  </bpmndi:BPMNPlane>
</bpmndi:BPMNDiagram>
```

---

## Files Requiring BPMNDI (13 remaining)

```yaml
revenue_cycle_subprocess:
  - SP-RC-002_Pre_Service.bpmn        # 5 tasks, 2 gateways
  - SP-RC-003_Clinical_Service.bpmn   # 7 tasks, 2 gateways
  - SP-RC-004_Clinical_Production.bpmn # 7 tasks, 2 gateways
  - SP-RC-005_Coding_Audit.bpmn       # 8 tasks, 1 gateway
  - SP-RC-006_Billing_Submission.bpmn # 10 tasks, 2 gateways (largest)
  - SP-RC-007_Denial_Management.bpmn  # 9 tasks, 1 gateway
  - SP-RC-008_Revenue_Collection.bpmn # 8 tasks, 1 gateway
  - SP-RC-009_Analytics_Intelligence.bpmn # 8 tasks, 3 gateways
  - SP-RC-010_Maximization.bpmn       # 9 tasks, 4 gateways (most complex)

orphaned_files:
  - glosa_management.bpmn
  - clinical_workflow.bpmn
  - integration_analytics.bpmn
  - revenue_optimization.bpmn
```

---

## Validation Checklist

```bash
# 1. XML Validation
xmllint --noout ${file}.bpmn && echo "✅ XML Valid"

# 2. Shape Count Matches Elements
grep -c '<bpmndi:BPMNShape' ${file}.bpmn
# Should match: startEvents + tasks + gateways + endEvents + boundaryEvents

# 3. Edge Count Matches Flows
grep -c '<bpmndi:BPMNEdge' ${file}.bpmn
# Should match: grep -c '<bpmn:sequenceFlow' ${file}.bpmn

# 4. bpmnElement References Valid
# Each bpmnElement attribute should reference an existing element ID

# 5. Optional: Camunda Modeler Import
# Open file in Camunda Modeler to verify visual rendering
```

---

## Estimated Effort per File

| Complexity | Tasks | Gateways | Est. Time |
|------------|-------|----------|-----------|
| Simple | 5-6 | 1-2 | 5-8 min |
| Medium | 7-8 | 2-3 | 8-12 min |
| Complex | 9-10 | 3-4 | 12-15 min |

**Total for 13 files: ~90-120 minutes**

---

## Safety Guarantees

```yaml
what_changes:
  - Adds <bpmndi:BPMNDiagram> section at end of file
  - Increases file line count (~100-150 lines added)

what_does_NOT_change:
  - Process ID
  - Task IDs
  - Topic names
  - Sequence flow IDs
  - Error definitions
  - Business logic
  - Execution semantics
```

---

*Pattern validated on 2026-02-14. Ready for batch execution.*
