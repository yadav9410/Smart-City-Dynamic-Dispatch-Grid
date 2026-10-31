# Configure Streamlit Cloud secrets

The app reads secrets from Streamlit Community Cloud's secret manager. Pasting credentials into a chat does not configure your deployed app.

## Rotate credentials first

The Groq API key and Neon connection string were exposed in a chat. Treat them as compromised:

1. Revoke the exposed Groq key and create a replacement in the Groq console.
2. In Neon, choose the project and branch, open **Roles**, reset the password for the database role, then use **Connect** to copy the fresh connection string.
3. Update your deployment with only the replacement values.

## Add secrets

Open the deployed app, click **Manage app → Settings → Secrets** and paste the following TOML template. Replace each placeholder with your own fresh value. Do not put real values in GitHub or this ZIP.

```toml
GROQ_API_KEY = "PASTE_NEW_ROTATED_GROQ_KEY_HERE"
DATABASE_URL = "PASTE_NEW_ROTATED_NEON_CONNECTION_STRING_HERE"
OPERATOR_PASSWORD_HASH = "PASTE_GENERATED_PBKDF2_HASH_HERE"
AGENT_MODEL = "openai/gpt-oss-120b"
```

Click **Save** and wait for the app to restart.

- The voice-availability note disappears when `GROQ_API_KEY` is configured.
- The report-storage note disappears when `DATABASE_URL` is configured.
- Report storage also requires the Phase 16.2 PostgreSQL schema. If it is not initialized, initialize it once from a trusted environment using the project's `initialize_database()` helper.

The public app deliberately does not print secret values or detailed connection errors.
