# Publishing to GitHub

This submission package contains the complete source tree but excludes local `.git` metadata. It has **not** been published to GitHub because GitHub account authorization was not granted in this session; no remote repository was created and no source was uploaded.

After unzipping the project, enabling/authorizing GitHub, and choosing whether the repository should be public or private:

1. Create an empty GitHub repository named `crossword-agent` (do not initialize it with a README or license; these files already exist here).
2. From the extracted project folder, initialize Git, set the commit author identity you want displayed, and commit:

   ```bash
   git init --initial-branch=main
   git config user.name "Your Name"
   git config user.email "your-github-email-or-noreply-address"
   git add -A
   git commit -m "Build constraint-driven crossword agent"
   ```

3. Add the URL of the repository you created and push:

   ```bash
   git remote add origin https://github.com/YOUR-USERNAME/crossword-agent.git
   git push -u origin main
   ```

Do not add API keys to Git. `.env` is ignored; copy `.env.example` and keep the real file local. The downloaded CC BY-NC-SA puzzles and converted gold corpus are local-only and ignored by Git; do not stage or publish `data/real_benchmark/` or `results/live/`.
