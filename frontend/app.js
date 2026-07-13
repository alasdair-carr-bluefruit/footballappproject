// Entry point — registers every screen's DOM listeners by importing each
// module (side-effect imports; each module wires up its own event handlers
// at load time). See docs/refactor/app-js-dependency-map.md for the module
// boundaries and the dependency graph these imports form.
//
// Load order matters: state.js must resolve first (everything depends on
// it), and pitch.js/setup-form.js before season.js/tournament.js/screens.js
// (which call into them). ES modules dedupe repeat imports via the module
// cache, so this is really just documentation of the graph, not a strict
// requirement — but keeping it in dependency order makes the graph legible.
import "./state.js";
import "./pitch.js";
import "./setup-form.js";
import "./season.js";
import "./tournament.js";
import "./screens.js";
