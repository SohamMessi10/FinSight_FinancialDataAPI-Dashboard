# AWS EC2 Deployment Guide

> **Status: documented, not executed.** This guide was written to be
> followed step-by-step, but it has **not** been run against a real AWS
> account in this session -- no EC2 instance was launched, and this project
> has not been deployed to or verified on EC2. Everything in this document
> is the intended procedure, not a report of a completed deployment. Treat
> each step as untested until you've run it yourself once.
>
> What *was* verified in this session: every Python module runs and passes
> its tests locally, and the full pipeline (ingestion -> Postgres -> API ->
> ML -> dashboard) was run end-to-end outside Docker. `docker-compose.yml`
> was validated for syntax but `docker-compose up --build` could not
> complete in the build sandbox because it blocks Docker Hub image pulls
> (see `reports/case_study.md`, Limitations). Budget time for that to be
> the first thing you debug on EC2 if it doesn't work immediately.

## 1. Launch an EC2 instance

1. In the AWS Console, go to **EC2 -> Launch Instance**.
2. **AMI:** Ubuntu Server 22.04 LTS (or newer).
3. **Instance type:** `t3.medium` (2 vCPU / 4 GB) is a reasonable minimum
   for Postgres + API + Streamlit together; `t3.small` will be tight once
   500 tickers x 500 days of history are loaded.
4. **Key pair:** create or select one you have the private key for --
   you'll need it for SSH.
5. **Storage:** 20 GB gp3 is comfortable (250k+250k rows of price/MA data
   plus Docker images is a few GB at most).

## 2. Configure the security group

Open only what's needed:

| Type | Port | Source | Purpose |
|---|---|---|---|
| SSH | 22 | your IP only (`x.x.x.x/32`) | admin access |
| Custom TCP | 8000 | your IP, or `0.0.0.0/0` if the API should be public | FastAPI |
| Custom TCP | 8501 | your IP, or `0.0.0.0/0` if the dashboard should be public | Streamlit |

Do **not** open 5432 (Postgres) to the internet -- the `postgres` service
in `docker-compose.yml` only needs to be reachable from the `api` service
on the same Docker network, not from outside the instance.

## 3. Install Docker and Docker Compose

SSH in, then:

```bash
ssh -i your-key.pem ubuntu@<ec2-public-ip>

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker

docker --version
docker compose version
```

## 4. Pull the repository

```bash
git clone https://github.com/<your-org-or-user>/FinSight_FinancialDataAPI-Dashboard.git
cd FinSight_FinancialDataAPI-Dashboard
```

(Use HTTPS with a personal access token, or set up a deploy key, depending
on whether the repo is private.)

## 5. Set environment variables / secrets

The defaults baked into `docker-compose.yml` (`finsight`/`finsight`) are
fine for a quick demo but should be overridden for anything beyond that.
Create a `.env` file next to `docker-compose.yml` (docker compose loads it
automatically) and reference the variables from there instead of hardcoding
them in the compose file:

```bash
cat > .env << 'EOF'
POSTGRES_USER=finsight
POSTGRES_PASSWORD=<use a real generated secret, not this>
POSTGRES_DB=finsight
EOF

chmod 600 .env
```

Then update `docker-compose.yml`'s `environment:` blocks to read
`${POSTGRES_PASSWORD}` etc. instead of the literal `finsight` value, and
never commit `.env` to git (add it to `.gitignore`).

## 6. Bring the stack up

```bash
docker compose up --build -d
docker compose ps
```

Expect three services healthy: `postgres`, `api`, `dashboard`. Then trigger
the first data load:

```bash
curl -X POST "http://localhost:8000/ingest?limit=500&days=500"
```

This is a ~30-second (ingestion) + ~2-minute (anomaly detection) call for
the full 500-ticker universe -- see the real timings measured locally in
`reports/case_study.md`. Expect EC2 to be roughly comparable or slower on a
`t3.medium`.

## 7. Verify

```bash
curl http://<ec2-public-ip>:8000/health
curl http://<ec2-public-ip>:8000/tickers | head -c 300
```

Open `http://<ec2-public-ip>:8501` in a browser for the dashboard.

## 8. Operational notes for a real deployment (not just a demo)

- Put the API and dashboard behind an ALB or Nginx with TLS instead of
  exposing raw ports 8000/8501 -- this guide's security group is
  demo-appropriate, not production-appropriate.
- Move Postgres to RDS instead of the `postgres` container once this is
  more than a demo, so data survives instance replacement; point
  `DATABASE_URL` (see `app/db.py`) at the RDS endpoint instead of the
  `postgres` service name.
- Set up a scheduled `POST /ingest` (cron, or an EventBridge rule hitting
  the endpoint) instead of triggering it manually.
- `docker compose logs -f api` / `dashboard` / `postgres` for
  troubleshooting; `docker compose down` to tear down (add `-v` to also
  drop the Postgres volume, which deletes all ingested data).
