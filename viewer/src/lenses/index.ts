// Lens framework entry point (P6-1). Importing this module registers the
// built-in lenses (Structure today; later lenses add their own import here) and
// re-exports the registry API. The store imports this for the side-effect
// registration plus the resolver helpers.
import "./structure";
import "./activity";

export * from "./registry";
export { structureLens, STRUCTURE_QUESTIONS } from "./structure";
export { activityLens, ACTIVITY_QUESTIONS } from "./activity";
