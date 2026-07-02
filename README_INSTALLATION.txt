Zuhause am Bach Mobile – FEHLERFREIES GitHub Pages Paket

Einbau:
1. ZIP entpacken.
2. Den gesamten Inhalt ins GitHub-Repository kopieren:
   - Ordner docs/
   - Ordner .github/workflows/
3. Commit & Push.
4. GitHub > Settings > Pages:
   Source = GitHub Actions.
5. Actions laufen lassen.

Wichtig:
- Nicht den ZIP-Ordner selbst hochladen.
- docs/index.html muss existieren.
- Der Workflow veröffentlicht exakt ./docs.
- deploy-pages@v4 wird verwendet.
- concurrency bricht alte hängende Deployments ab.

Wenn ein Deployment hängt:
Actions > laufende alte Deployments abbrechen.
Dann neuen Commit oder Workflow Dispatch starten.
