// Lens framework entry point (P6-1). Importing this module registers the
// built-in lenses (Structure today; later lenses add their own import here) and
// re-exports the registry API. The store imports this for the side-effect
// registration plus the resolver helpers.
import "./structure";
import "./inventory";
import "./activity";
import "./flow";
import "./capability";
import "./data";
import "./rules";
import "./design";

export * from "./registry";
export { structureLens, STRUCTURE_QUESTIONS } from "./structure";
export {
  inventoryLens,
  INVENTORY_QUESTIONS,
  collectCriticalComponents,
  collectExternalDependencies,
  collectListeningPorts,
  hasCriticalityData,
  type CriticalEntry,
  type DependencyEntry,
  type PortEntry,
} from "./inventory";
export { activityLens, ACTIVITY_QUESTIONS } from "./activity";
export {
  flowLens,
  FLOW_QUESTIONS,
  hasFlowData,
  collectFlowComponents,
  buildFlowEdges,
  buildAdjacency,
  walkFlow,
  rankEntryFlows,
  collectActionEdges,
  FLOW_COMPONENT_TYPES,
  FLOW_EDGE_TYPES,
  FLOW_ACTION_EDGE_TYPE,
  type FlowEntry,
} from "./flow";
export {
  capabilityLens,
  CAPABILITY_QUESTIONS,
  CAP_KIND_ORDER,
  hasCapabilities,
  capabilityIsTested,
  collectCapabilityOwnerIds,
  groupCapabilitiesByKind,
  capabilityCountsByComponent,
  buildCapabilityGraph,
  type CapabilityGroup,
  type CapabilityKindCounts,
} from "./capability";
export {
  dataLens,
  DATA_QUESTIONS,
  ENTITY_KIND_ORDER,
  READ_EDGE_TYPE,
  WRITE_EDGE_TYPE,
  hasDataEntities,
  collectEntityOwnerIds,
  accessCountForEntity,
  rankEntitiesByAccess,
  collectEntityAccessors,
  buildEntityEgoGraph,
  buildDataLandingGraph,
  type EntityGroup,
  type EntityAccessor,
} from "./data";
export {
  rulesLens,
  RULE_QUESTIONS,
  RULE_KIND_ORDER,
  DECISION_ANCHORS,
  hasRules,
  ruleEntityId,
  ruleCapabilityId,
  collectRuleOwnerIds,
  ruleCountsByComponent,
  groupRulesByKind,
  decisionTableFromRule,
  buildRulesGraph,
  type RuleKindCounts,
  type RuleComponentGroup,
  type RuleKindGroup,
  type RuleDecisionTable,
} from "./rules";
export {
  designLens,
  DESIGN_QUESTIONS,
  DESIGN_KIND_ORDER,
  DESIGN_KIND_LABEL,
  METHOD_LABEL,
  ZONE_OF_PAIN_MAX_SUM,
  ZONE_OF_USELESSNESS_MIN_SUM,
  hasDesignSignals,
  designMethodCaveat,
  groupDesignFindings,
  findDesignFinding,
  findingComponentIds,
  findingImplicatesEdge,
  buildScatter,
  zoneFor,
  collectDesignSubjectIds,
  buildDesignFindingGraph,
  buildDesignLandingGraph,
  readZoneThresholds,
  computeBlastRadius,
  blastRadiusFrom,
  buildBlastAdjacency,
  type BlastRadius,
  type DesignFindingGroup,
  type ScatterPoint,
  type ScatterData,
  type ZoneThresholds,
} from "./design";
