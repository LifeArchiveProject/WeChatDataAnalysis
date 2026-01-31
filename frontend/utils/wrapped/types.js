// JSDoc types for the Wrapped API (kept in JS to match the current codebase).

/**
 * @typedef {Object} WrappedCardBase
 * @property {number} id
 * @property {string} title
 * @property {'global'} scope
 * @property {'A'|'B'|'C'|'D'|'E'} category
 * @property {'ok'|'error'|'idle'|'loading'} status
 * @property {string} kind
 * @property {string} narrative
 * @property {Record<string, any>} data
 */

/**
 * @typedef {Object} WrappedCardManifest
 * @property {number} id
 * @property {string} title
 * @property {'global'} scope
 * @property {'A'|'B'|'C'|'D'|'E'} category
 * @property {string} kind
 */

/**
 * @typedef {Object} WrappedAnnualMetaResponse
 * @property {string} account
 * @property {number} year
 * @property {'global'} scope
 * @property {number[]|undefined} availableYears
 * @property {WrappedCardManifest[]} cards
 */

/**
 * @typedef {Object} WrappedAnnualResponse
 * @property {string} account
 * @property {number} year
 * @property {'global'} scope
 * @property {string|null} username
 * @property {number} generated_at
 * @property {boolean} cached
 * @property {number[]|undefined} availableYears
 * @property {WrappedCardBase[]} cards
 */

export {}
