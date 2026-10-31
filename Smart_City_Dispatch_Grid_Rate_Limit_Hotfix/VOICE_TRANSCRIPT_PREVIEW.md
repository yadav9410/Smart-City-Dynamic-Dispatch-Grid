# Voice transcript preview update

After you record audio, the app now immediately displays an editable **Transcript (editable)** box below the recording controls.

## How it works

1. Record your description.
2. The empty transcript box appears immediately, so the user knows where the recognized words will appear.
3. Keep the separate consent checkbox enabled and click **Convert recording to text**.
4. When Groq transcription succeeds, the recognized words populate the box.
5. Review or correct the words, then click **Use this text in the incident description**.
6. Submit the incident separately using the report-storage, location-storage, and prototype acknowledgements.

Recording audio is not itself speech-to-text. To protect privacy, the recording is not sent automatically. It is sent to Groq only after the user explicitly consents and clicks the transcription button.

## If the transcript box remains empty

- Confirm `GROQ_API_KEY` is present in Streamlit Community Cloud → Manage app → Settings → Secrets.
- Confirm the key is active and has access to the speech-to-text API/model.
- Confirm transcription consent is checked.
- Click **Convert recording to text** and wait for the result.
- If the key is missing, the app explains that automatic transcription is unavailable; the text box still supports manual typing.

Do not put API keys in GitHub or source code. The app does not save raw audio to PostgreSQL or files.
