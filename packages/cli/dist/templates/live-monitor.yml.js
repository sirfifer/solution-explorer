export function liveMonitorWorkflow(options) {
    const r2Steps = options.liveMode === "cloudflare"
        ? `

      - name: Upload to Cloudflare R2
        if: \${{ secrets.CF_WORKER_URL != '' }}
        env:
          AWS_ACCESS_KEY_ID: \${{ secrets.CF_R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: \${{ secrets.CF_R2_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: auto
        run: |
          PROJECT_ID="\${{ github.event.repository.name }}"
          ENDPOINT="\${{ secrets.CF_R2_ENDPOINT }}"
          BUCKET="solution-explorer-data"

          for file in .arch-output/live/*.json; do
            filename=$(basename "$file")
            aws s3 cp "$file" "s3://\${BUCKET}/\${PROJECT_ID}/\${filename}" \\
              --endpoint-url "$ENDPOINT" \\
              --content-type "application/json"
          done

          aws s3 cp .arch-output/architecture.json \\
            "s3://\${BUCKET}/\${PROJECT_ID}/manifest.json" \\
            --endpoint-url "$ENDPOINT" \\
            --content-type "application/json"

      - name: Notify Cloudflare Worker
        if: \${{ secrets.CF_WORKER_URL != '' }}
        run: |
          PROJECT_ID="\${{ github.event.repository.name }}"

          COMPONENT_COUNT=$(python3 -c "
          import json
          with open('.arch-output/architecture.json') as f:
              arch = json.load(f)
          def count(comps):
              return sum(1 + count(c.get('children', [])) for c in comps)
          print(count(arch.get('components', [])))
          ")

          RELATIONSHIP_COUNT=$(python3 -c "
          import json
          with open('.arch-output/architecture.json') as f:
              arch = json.load(f)
          print(len(arch.get('relationships', [])))
          ")

          VERSION=$(python3 -c "
          import json
          with open('.arch-output/live/version.json') as f:
              print(json.load(f)['version'])
          ")

          COMMIT_MSG=$(python3 -c "
          import json
          msg = '''\${{ github.event.head_commit.message || 'workflow dispatch' }}'''
          print(json.dumps(msg[:200]))
          ")

          curl -s -o /dev/null -w '' \\
            -X POST '\${{ secrets.CF_WORKER_URL }}/ingest' \\
            -H 'Authorization: Bearer \${{ secrets.CF_INGEST_TOKEN }}' \\
            -H 'Content-Type: application/json' \\
            -d "{
              \\"project_id\\": \\"\${PROJECT_ID}\\",
              \\"version\\": \${VERSION},
              \\"commit_sha\\": \\"\${{ steps.sha.outputs.sha }}\\",
              \\"commit_message\\": \${COMMIT_MSG},
              \\"component_count\\": \${COMPONENT_COUNT},
              \\"relationship_count\\": \${RELATIONSHIP_COUNT}
            }"`
        : "";
    return `name: Live Monitor

on:
  push:
    branches: [main]
  workflow_run:
    workflows: ["Architecture Visualization"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: live-monitor-\${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read
  pages: write
  id-token: write
  actions: read

jobs:
  update-and-deploy:
    name: Update Architecture & Deploy Live Data
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: \${{ steps.deploy.outputs.page_url }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Checkout Solution Explorer
        uses: actions/checkout@v4
        with:
          repository: sirfifer/solution-explorer
          path: .solution-explorer

      - name: Install Dependencies
        run: |
          if [ -f ".solution-explorer/pyproject.toml" ]; then
            pip install -e ".solution-explorer[live]" 2>/dev/null || echo "Optional deps unavailable, using stdlib only"
          fi

      - name: Determine Commit SHA
        id: sha
        run: |
          if [ "\${{ github.event_name }}" = "workflow_run" ]; then
            echo "sha=\${{ github.event.workflow_run.head_sha }}" >> "$GITHUB_OUTPUT"
          else
            echo "sha=\${{ github.sha }}" >> "$GITHUB_OUTPUT"
          fi

      - name: Restore Architecture Baseline
        uses: actions/cache/restore@v4
        with:
          path: .arch-baseline
          key: arch-baseline-\${{ github.ref }}

      - name: Run Architecture Analyzer
        run: |
          mkdir -p .arch-output/live

          if [ -f "solution-explorer.json" ]; then
            python3 .solution-explorer/analyze.py --config solution-explorer.json \\
              -o .arch-output/architecture.json --compact
          else
            python3 .solution-explorer/analyze.py . \\
              -o .arch-output/architecture.json --compact
          fi

      - name: Collect CI Status
        env:
          GITHUB_TOKEN: \${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/collect-ci-status.py \\
            --repo "\${{ github.repository }}" \\
            --sha "\${{ steps.sha.outputs.sha }}" \\
            -o .arch-output/live/status-overlay.json

      - name: Generate version.json
        run: |
          python3 -c "
          import json, time, datetime
          data = {
              'version': int(time.time()),
              'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'commit_sha': '\${{ steps.sha.outputs.sha }}'
          }
          with open('.arch-output/live/version.json', 'w') as f:
              json.dump(data, f, indent=2)
          "

      - name: Generate live-config.json
        run: |
          python3 -c "
          import json, os
          repo = '\${{ github.repository }}'
          owner, repo_name = repo.split('/')
          worker_url = os.environ.get('CF_WORKER_URL', '')

          mode = 'cloudflare' if worker_url else 'github'
          data_url = f'https://{owner}.github.io/{repo_name}/live'

          config = {
              'enabled': True,
              'data_url': data_url,
              'backend_mode': mode,
              'polling': {
                  'default_interval_seconds': 15 if mode == 'cloudflare' else 30,
                  'min_interval_seconds': 10 if mode == 'cloudflare' else 15,
                  'idle_interval_seconds': 60 if mode == 'cloudflare' else 120,
                  'adaptive': True,
                  'pause_when_hidden': True
              },
              'features': {
                  'activity_log': True,
                  'admin_dashboard': True,
                  'version_history': True,
                  'ci_status_overlay': True,
                  'realtime_ci_webhooks': mode == 'cloudflare',
                  'realtime_push': False
              }
          }
          if worker_url:
              config['worker_url'] = worker_url
              config['project_id'] = repo_name
          with open('.arch-output/live/live-config.json', 'w') as f:
              json.dump(config, f, indent=2)
          "
        env:
          CF_WORKER_URL: \${{ secrets.CF_WORKER_URL }}

      - name: Generate Admin Summary
        env:
          GITHUB_TOKEN: \${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/generate-admin-summary.py \\
            --arch .arch-output/architecture.json \\
            --version .arch-output/live/version.json \\
            --repo "\${{ github.repository }}" \\
            --sha "\${{ steps.sha.outputs.sha }}" \\
            -o .arch-output/live/admin-summary.json

      - name: Copy Architecture to Live Directory
        run: cp .arch-output/architecture.json .arch-output/live/architecture.json

      - name: Save Architecture Baseline
        uses: actions/cache/save@v4
        with:
          path: .arch-baseline
          key: arch-baseline-\${{ github.ref }}-\${{ steps.sha.outputs.sha }}

      - name: Upload Pages Artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .arch-output/live

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4${r2Steps}
`;
}
