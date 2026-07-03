// Barrel re-export so callers keep importing `./pages/Board` after the promotion
// from a flat file to a page-scoped folder (rule 9 in ../CLAUDE.md).
export { Board } from "./Board";
