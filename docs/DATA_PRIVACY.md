# Data privacy

## 1. Summary

PRISM is designed to analyse code without becoming a place where that code accumulates.
It has **no database**, writes **no cache** of third-party content, requires **no account**,
and makes **no outbound request** except to the GitHub REST API when you explicitly ask it to
review a pull request.

## 2. What PRISM processes

| Data | Source | Where it goes |
| --- | --- | --- |
| Diff text | Your file, stdin, `git diff`, or the GitHub files API | Memory only. Parsed as text. Never written to disk by PRISM |
| File paths, line numbers, code snippets | The diff | Into findings, and into the report you asked for. Snippets are capped in length |
| PR metadata (title, author, branch, SHAs) | The GitHub API | Into the report header. Sanitised before rendering |
| GitHub token (optional) | Environment variable | Only into the `Authorization` header of the API request. Never logged, never reported |
| Coverage report | A path *you* configure | Read once, size-capped, parsed for line hits |
| Reports | Produced by PRISM | Written to the path you specify, or returned in the API response |

## 3. What PRISM does **not** do

- No telemetry, analytics, crash reporting or "phone home" of any kind.
- No writing of analysed repository content to disk, a database, or a cache.
- No persistence of GitHub responses between runs.
- No collection of personal data beyond the PR author's public login, which appears in the
  report because a review header needs it.
- No sending of code to a language model. There is no LLM provider in this build, and the
  extension point is disabled by default.
- No posting of anything to GitHub. PRISM never comments, pushes or changes settings.

## 4. Token handling

| Aspect | Behaviour |
| --- | --- |
| Where it may live | `PRISM_GITHUB_TOKEN` or `GITHUB_TOKEN` in the environment; optionally a `.env` file you keep out of version control |
| Required? | No. Public pull requests work anonymously |
| Recommended scope | Read-only (`public_repo`, or `repo` only if you must review a private repository) |
| How it is transmitted | HTTPS `Authorization: Bearer …` header to `api.github.com` only |
| How it is stored | PRISM does not store it. It lives in process memory for the duration of the request |
| How it is disclosed | As a boolean (`github_token_configured`) and never as a value |
| Log protection | A `RedactionFilter` on every log handler scrubs token-shaped strings |
| Error protection | Domain errors carry a code and a message; `redact()` is applied to configuration values that reach an error |
| Repository protection | `.gitignore` excludes `.env` and key files; `.dockerignore` keeps them out of the image; a CI step fails if `.env` is ever tracked |

## 5. Reports are potential data-leak surfaces

A report contains file paths and short code snippets from the reviewed change. Treat it the
way you would treat a patch:

- Do not commit reports from a private repository into a public repository.
- `evidence/` is excluded by `.gitignore` by default for exactly this reason.
- Found secret values are **masked** in findings (first four and last four characters only).
  The presence of a finding means a credential may exist in your history — rotate it rather
  than relying on the masking.
- The API does not return filesystem paths or environment values; a test asserts this for every
  endpoint.

## 6. Request-for-review of a private repository

If you review a **private** repository:

1. PRISM needs a token with read access to that repository.
2. The diff content is fetched over HTTPS to your machine and held in memory.
3. The report is written only where you tell it to be written.
4. Nothing is sent anywhere else — there is no third-party service in the data path.

## 7. Data retention

PRISM itself retains nothing. Retention is entirely your choice, determined by where you write
reports and how long you keep them. If you want no retention at all, write the report to a
temporary location or use the API and discard the response.

## 8. Container considerations

The image runs as uid 10001 with a read-only root filesystem, all capabilities dropped,
`no-new-privileges`, and a `noexec` tmpfs at `/tmp`. Uploaded or generated artefacts cannot be
executed inside the container, and nothing persists across a container restart.

## 9. Lawful basis and jurisdiction

This section is deliberately empty of claims. PRISM is a local developer tool that processes
what you give it; determining whether your use is lawful in your jurisdiction — particularly
if you review third-party code or operate an instance for others — is your responsibility, not
a property of the tool. No compliance certification is claimed.
