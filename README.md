# KuCoin NEAR Basis RL Bot

Repository for automatic basis trading between:
- Spot: `NEAR-USDT`
- Futures perpetual: `NEARUSDTM`

The strategy is delta-neutral basis mean-reversion with RL decision making:
- baseline z-score policy
- Q-learning agent trained on basis features
- live/shadow execution through KuCoin SDK

Current runtime mode: `RL-only` (no baseline fallback in live decisions).

## Repository structure (lecture16-style)

- `notebooks/lecture16_basis_rl_colab.ipynb` - lecture16-style notebook entrypoint.
- `notebooks/lecture17_near_basis_rl.ipynb` - same demo notebook (alias copy).
- `trade_signal_executor_kucoin.py` - main CLI executor (`train` / `shadow` / `live`).
- `run_trade_signal.py` - cross-platform launcher.
- `run_kucoin_trade_signal.ps1` - Windows wrapper.
- `run_kucoin_trade_signal.sh` - macOS/Linux wrapper.
- `src/kucoin_near_basis_rl/*.py` - RL + feature engineering + KuCoin data/execution layer.
- `config/micro_near_v1_1m.json` - main 1-minute profile.
- `config/micro_near_v1.json` - alternative 15-minute profile.
- `MODEL_SPEC.md` - formal model/reward/risk description.

## 1) Install

```bash
python -m venv venv
```

Windows:
```powershell
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel "setuptools<81"
python -m pip install -r requirements.txt
```

macOS/Linux:
```bash
source venv/bin/activate
python -m pip install --upgrade pip wheel "setuptools<81"
python -m pip install -r requirements.txt
chmod +x run_kucoin_trade_signal.sh
```

All-in-one scripts package:

Windows PowerShell:
```powershell
.\scripts\bot.ps1 -Action install
.\scripts\bot.ps1 -Action env-template
.\scripts\bot.ps1 -Action train-fast
.\scripts\bot.ps1 -Action shadow-once
```

macOS/Linux:
```bash
chmod +x scripts/bot.sh
./scripts/bot.sh install
./scripts/bot.sh env-template
./scripts/bot.sh train-fast
./scripts/bot.sh shadow-once
```

## Docker

Build image:

```bash
docker build -t lecture17-kucoin-rl .
```

One-command live (PowerShell):

```powershell
.\scripts\bot.ps1 -Action docker-live-up
```

The script auto-removes old `near-rl-live` container name conflicts before start.

One-command live (bash):

```bash
./scripts/bot.sh docker-live-up
```

One-command logs/stop:

```powershell
.\scripts\bot.ps1 -Action docker-live-logs
.\scripts\bot.ps1 -Action docker-live-down
```

Run train:

```powershell
docker run --rm -it -v ${PWD}/models:/app/models -v ${PWD}/reports:/app/reports -v ${PWD}/.runtime:/app/.runtime lecture17-kucoin-rl python run_trade_signal.py --mode train --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json --features-out reports/near_basis_features.csv --env-file .runtime/kucoin.env
```

Run shadow once:

```powershell
docker run --rm -it -v ${PWD}/models:/app/models -v ${PWD}/.runtime:/app/.runtime lecture17-kucoin-rl python run_trade_signal.py --mode shadow --once --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json --env-file .runtime/kucoin.env
```

Run continuous live:

```powershell
docker run -d --name near-rl-live --restart unless-stopped -v ${PWD}/models:/app/models -v ${PWD}/.runtime:/app/.runtime lecture17-kucoin-rl python run_trade_signal.py --mode live --run-real-order --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json --env-file .runtime/kucoin.env
```

Live logs:

```bash
docker logs -f near-rl-live
```

Stop live container:

```bash
docker rm -f near-rl-live
```

## 2) API credentials

Create local file `.runtime/kucoin.env` (ignored by git):

```env
KUCOIN_API_KEY=...
KUCOIN_API_SECRET=...
KUCOIN_API_PASSPHRASE=...
```

Notes:
- `KUCOIN_API_PASSPHRASE` is required by KuCoin SDK for live trading.
- Current project auto-loads `.runtime/kucoin.env` in launcher/executor scripts.

## 3) Train model

```powershell
python run_trade_signal.py --mode train --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json --features-out reports/near_basis_features.csv
```

Optional train range:
```powershell
python run_trade_signal.py --mode train --start "2026-01-01T00:00:00Z" --end "2026-03-01T00:00:00Z"
```

Fast smoke-train (recommended first run):
```powershell
python run_trade_signal.py --mode train --episodes 10 --start "2026-03-10T00:00:00Z" --end "2026-03-11T00:00:00Z"
```

## 4) Shadow mode (paper)

One cycle:
```powershell
python run_trade_signal.py --mode shadow --once --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json
```

Loop:
```powershell
python run_trade_signal.py --mode shadow --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json
```

## 5) Live mode (real orders)

```powershell
python run_trade_signal.py --mode live --run-real-order --config config/micro_near_v1_1m.json --model-path models/near_basis_qlearning.json
```

Or with wrapper:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_kucoin_trade_signal.ps1 -Mode live -RunRealOrder
```

## 6) Notebook

Open:
- `notebooks/lecture16_basis_rl_colab.ipynb`

Notebook shows:
1. Download/prepare KuCoin candles.
2. Build basis features (`volume`, `volatility`, `z-score`, etc).
3. Train RL model.
4. Run one paper decision tick.

Note:
- `tick["action_source"]` in logs shows `rl_known_state` or `rl_new_state`.

## 7) Common issues

- `Missing required env vars for live mode`:
  fill `.runtime/kucoin.env` with key/secret/passphrase.
- `Invalid KC-API-PASSPHRASE`:
  passphrase does not match API key.
- `ConnectionError`:
  check firewall/network access to `api.kucoin.com` and `api-futures.kucoin.com`.
- `pkg_resources` / `NameError` from `kucoin-python`:
  run `python -m pip install "setuptools<81"` and retry.
- `ModuleNotFoundError: gymnasium / gym`:
  run `python -m pip install -r requirements.txt` again (the package list includes `gymnasium`).

## 8) Security

- Do not commit `.runtime/kucoin.env`.
- Use IP restrictions for API keys in production.
- Start from `shadow` mode before enabling `live`.

## 9) Publish to GitHub

```bash
git init
git add .
git commit -m "KuCoin NEAR basis RL bot"
git branch -M main
git remote add origin https://github.com/<your_user>/<your_repo>.git
git push -u origin main
```

## 10) Scripts package actions

`scripts/bot.ps1` and `scripts/bot.sh` support:
- `install`
- `env-template`
- `train-fast`
- `train`
- `shadow-once`
- `shadow`
- `live`
- `test`
- `notebook`
- `docker-build`
- `docker-shadow-once`
- `docker-live-up`
- `docker-live-logs`
- `docker-live-down`
