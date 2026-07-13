// Plain JavaScript helper to exercise the javascript parser.

export function formatUser(user) {
  return `${user.name} (#${user.id})`;
}

export const DEFAULT_GREETING = "hello";

export class Formatter {
  constructor(prefix) {
    this.prefix = prefix;
  }

  apply(text) {
    return this.prefix + text;
  }
}
