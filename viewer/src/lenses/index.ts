// Lens framework entry point (P6-1). Importing this module registers the
// built-in lenses (Structure today; later lenses add their own import here) and
// re-exports the registry API. The store imports this for the side-effect
// registration plus the resolver helpers.
import "./structure";
import "./activity";
import "./flow";
import "./capability";
import "./data";

export * from "./registry";
export { structureLens, STRUCTURE_QUESTIONS } from "./structure";
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
