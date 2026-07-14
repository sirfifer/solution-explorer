// Lens framework entry point (P6-1). Importing this module registers the
// built-in lenses (Structure today; later lenses add their own import here) and
// re-exports the registry API. The store imports this for the side-effect
// registration plus the resolver helpers.
import "./structure";
import "./flow";

export * from "./registry";
export { structureLens, STRUCTURE_QUESTIONS } from "./structure";
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
import "./activity";

export { structureLens, STRUCTURE_QUESTIONS } from "./structure";
export { activityLens, ACTIVITY_QUESTIONS } from "./activity";

