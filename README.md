# KubeWeekly

Kubernetes Intelligence Agent: ingests Kubernetes/CNCF ecosystem news from a
broad set of sources, classifies and deduplicates it, scores importance,
detects trends, and composes a daily LinkedIn draft post for human review.

Pipeline: `sources → ingest → classify → dedup → score → trends → summarize
→ compose → draft`. See `/Users/apple/.claude/plans/kubernetes-intelligence-agent-would-cozy-hearth.md`
for the full design.

All common operations are wrapped in the `Makefile` — run `make help` for
the full list. Override `IMAGE`, `TAG`, or `NAMESPACE` as needed, e.g.
`make deploy NAMESPACE=kubeweekly-staging`.

## LLM provider

`LLM_PROVIDER` selects which provider powers classify/score/summarize/compose
— `deepseek` (default) or `claude`. Only the matching API key needs a real
value; the other can stay unset. DeepSeek is reached via the `openai` SDK
pointed at its OpenAI-compatible endpoint — see `src/kubeweekly/llm.py`.
Model names default per-provider (`deepseek-chat`, or
`claude-haiku-4-5`/`claude-sonnet-5`) but can be overridden with
`CLASSIFY_MODEL` / `SUMMARIZE_MODEL`.

## Local development

```bash
$EDITOR ~/.env   # set LLM_PROVIDER + the matching API key; GITHUB_TOKEN / NVD_API_KEY optional

make test      # create .venv, install deps, run pytest
make dry-run   # run the pipeline against a couple of sources, print the draft
make run       # full run against all of config/sources.yaml, writes to data/
```

Secrets live in `~/.env` (your home directory), not a file inside this repo
— `kubeweekly.main` loads it automatically via `python-dotenv` on every run.
Keeping it outside the project tree means it can never be committed, even by
accident. Exported shell env vars work too and take precedence over `~/.env`.

## Kubernetes deployment

```bash
# one-time: copy the secret template, fill in real values, apply it
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.local.yaml
$EDITOR deploy/k8s/secret.local.yaml   # fill in the key matching LLM_PROVIDER (see deploy/k8s/cronjob.yaml)
make secret                            # applies deploy/k8s/secret.local.yaml
# (or `make sync-secret` to regenerate deploy/k8s/secret.local.yaml straight
# from ~/.env instead of editing it by hand, then `make secret` to apply it)

make push                              # build + push the image to Docker Hub (IMAGE/TAG vars)
make deploy                            # apply namespace, PVC, ConfigMap, CronJob
make trigger                           # manually fire one run to smoke-test
make logs                              # tail the most recent pod's logs
make status                            # check the CronJob's schedule / recent Jobs / Pods
```

`IMAGE` defaults to `vasudevdchavan/kubeweekly`, `TAG` to `latest` — override
either as needed (`make push IMAGE=yourname/kubeweekly`). `deploy/k8s/cronjob.yaml`
ships with that same default baked in, so a fresh `make deploy` on an empty
cluster already points at the right image without needing `make set-image`.

`deploy/k8s/secret.local.yaml` is gitignored — never commit it.

To add/remove sources: edit `config/sources.yaml`, then `make deploy` again
— each `CronJob` run starts a fresh pod, so the next scheduled run picks up
the new source list. No image rebuild needed.

To ship a new image build without touching anything else: `make release`
(build, push, `kubectl apply -k .`, then point the CronJob at the new tag).
`make set-image` (what `release` uses under the hood) also fixes up
`imagePullPolicy` to match the tag — `Always` for `:latest` so the cluster
always pulls the newest push, `IfNotPresent` for any other tag so a local
build isn't re-pulled from a registry it was never pushed to. `kubectl set
image` alone only patches the image field, so switching tags without going
through `make set-image` can leave a stale policy in place and cause
`ErrImagePull`/`ImagePullBackOff`.

`make undeploy` tears down everything `make deploy` created, including the
PVC's data (SQLite history + drafts) — it does not touch the Secret.

**Local cluster (e.g. minikube), no registry needed:** `make local-deploy`
builds the image, loads it directly into the cluster (`MINIKUBE_PROFILE`,
default `homelab`), applies the manifests, points the `CronJob` at the local
image (with the correct `imagePullPolicy`), and regenerates+applies the
Secret from `~/.env` (`make sync-secret` does just that last part, if you
only need to push new key values). To go back to the registry image
afterwards: `make set-image` with no overrides (uses the `IMAGE`/`TAG`
defaults above).

## Layout

```
src/kubeweekly/
  sources/     connectors (RSS, GitHub, Artifact Hub, HN, Reddit, CVE, cloud, mailing lists)
  pipeline/    ingest, classify, dedup, score, trends, summarize
  llm.py       provider abstraction (Claude / DeepSeek) - see "LLM provider" above
  briefing/    compose + render the LinkedIn draft
  main.py      CLI entrypoint
config/sources.yaml   declarative source list (git-tracked source of truth)
deploy/               Dockerfile + Kubernetes manifests (CronJob, PVC, ConfigMap)
kustomization.yaml    root kustomization (generates the sources ConfigMap)
scripts/sync_secret.py  regenerates the k8s Secret from ~/.env (used by `make sync-secret`)
.dockerignore          keeps data/, .venv/, .git/ etc. out of the build context
Makefile              build/push/deploy/test targets — see `make help`
```
