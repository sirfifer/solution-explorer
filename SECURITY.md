# Security Policy

## Supported Versions

Only the latest release on the main branch is supported with security updates. We recommend always using the most recent version to ensure you have the latest security patches.

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in SysCorpus, please report it responsibly.

To report a vulnerability:

1. **Email the maintainer**: Send details to the email listed in the repository's maintainer profile.
2. **GitHub Security Advisory**: Alternatively, you can open a private security advisory on GitHub. Navigate to the repository's Security tab and select "Report a vulnerability" to create a private discussion with the maintainers.

Please include the following information:

- A clear description of the vulnerability
- Steps to reproduce the issue (if applicable)
- The potential impact
- Any suggested fixes or workarounds

**Do not** open a public issue or pull request for security vulnerabilities. This allows us time to investigate and develop a fix before the vulnerability becomes public.

## Security Considerations

### Python Analyzer

The Python analyzer (`analyze.py`) only reads and parses source files. It does not execute code, import modules, or run any user code. This significantly limits the attack surface compared to tools that perform code execution.

### Viewer Application

The viewer is a static client-side React/TypeScript application. It has no backend server, no database, and no server-side processing. All analysis happens locally in the user's environment. The viewer reads the JSON output from the analyzer and renders it in the browser without making external API calls (except to GitHub when using the GitHub Action integration).

### GitHub Action

The GitHub Action runs in your own CI environment (GitHub Actions runner) and does not send data to external servers. It executes the Python analyzer and produces an `architecture.json` file that you control. You are responsible for how you store and share this output.

## Response Time

We aim to acknowledge security reports within 48 hours and will work to develop and release a fix as quickly as possible. The timeline for a fix depends on the severity and complexity of the vulnerability.

Thank you for helping keep SysCorpus secure.
