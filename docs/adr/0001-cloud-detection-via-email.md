# Cloud vs Server/DC detection via JIRA_USER_EMAIL

The presence of the `JIRA_USER_EMAIL` environment variable switches the client to Cloud mode: Basic Auth (email:token) and the v3 search endpoint (`/rest/api/3/search/jql`). Without it, the client assumes Server/DC: Bearer token auth and the v2 search endpoint (`/rest/api/2/search`).

We chose to infer the deployment type from an auth credential rather than adding an explicit `JIRA_DEPLOYMENT_TYPE` flag. The reasoning: Cloud *requires* an email for Basic Auth while Server/DC never uses one, so the email's presence is a reliable signal with zero additional configuration. The alternative — a separate boolean or enum — would add a config knob that could contradict the auth setup (e.g. `DEPLOYMENT_TYPE=cloud` without providing an email), creating a class of misconfiguration that doesn't exist with the current approach.

The tradeoff: if Atlassian ever supports email-less Cloud auth or email-based Server/DC auth, this heuristic breaks. That hasn't happened in the API's history and would likely be a major migration event regardless.
