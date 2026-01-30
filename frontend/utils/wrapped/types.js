// JSDoc types for the Wrapped API (kept in JS to match the current codebase).

/**
 * @typedef {Object} WrappedCardBase
 * @property {number} id
 * @property {string} title
 * @property {'global'} scope
 * @property {'A'|'B'|'C'|'D'|'E'} category
 * @property {'ok'|'error'} status
 * @property {string} kind
 * @property {string} narrative
 * @property {Record<string, any>} data
 */

/**
 * @typedef {Object} WrappedAnnualResponse
 * @property {string} account
 * @property {number} year
 * @property {'global'} scope
 * @property {string|null} username
 * @property {number} generated_at
 * @property {boolean} cached
 * @property {WrappedCardBase[]} cards
 */

export {}

