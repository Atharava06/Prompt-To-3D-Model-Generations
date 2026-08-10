# CheapCUDA Recovery Runbook

Use this when the rented GPU is deleted and a new CheapCUDA machine is started.
This restores the backend/API/auth/history path only. It does not download SDXL
or Hunyuan model weights.

## Current Working Shape

- Frontend: `https://prompt-to-3d-frontend.vercel.app`
- Backend runs on the CheapCUDA public HTTP port, for example:
  `http://<GPU_IP>:<HTTP_PORT>`
- Supervisor service name on the GPU: `prompt-to-3d-backend`
- App path on the GPU: `/root/Prompt-to-3d`
- Backend path on the GPU: `/root/Prompt-to-3d/PT3-backend`
- Users, sessions, and jobs: Supabase Postgres
- Generated images and GLBs: Cloudflare R2 when `R2_*` env vars are set

## Fresh GPU Steps

1. Start a new CheapCUDA RTX 3090 machine.
2. Copy the SSH command from CheapCUDA, for example:

   ```bash
   ssh root@<GPU_IP> -p <SSH_PORT>
   ```

3. From this local repo, package and upload the app without heavy files:

   ```powershell
   $archive = "$env:TEMP\prompt-to-3d-backend-upload.tar.gz"
   if (Test-Path $archive) { Remove-Item $archive -Force }
   tar -czf $archive --exclude=.git --exclude=PT3-frontend/node_modules --exclude=PT3-frontend/dist --exclude=PT3-backend/venv --exclude=PT3-backend/.env --exclude=models --exclude=PT3-backend/output --exclude=PT3-backend/data .
   scp -P <SSH_PORT> $archive root@<GPU_IP>:/tmp/prompt-to-3d-backend-upload.tar.gz
   ```

4. SSH into the GPU and install the backend:

   ```bash
   rm -rf /root/Prompt-to-3d
   mkdir -p /root/Prompt-to-3d
   tar -xzf /tmp/prompt-to-3d-backend-upload.tar.gz -C /root/Prompt-to-3d
   cd /root/Prompt-to-3d/PT3-backend

   apt-get update -y
   DEBIAN_FRONTEND=noninteractive apt-get install -y \
     python3 python3-venv python3-pip supervisor curl \
     libgl1 libglib2.0-0 libgomp1

   python3 -m venv venv
   venv/bin/python -m pip install --upgrade pip wheel setuptools
   venv/bin/pip install -r requirements.txt
   ```

5. Create `/root/Prompt-to-3d/PT3-backend/.env`.
   Keep secrets private and do not commit this file.

   ```ini
   HOST=0.0.0.0
   PORT=<CHEAPCUDA_HTTP_PORT>
   RELOAD=false
   ALLOWED_ORIGINS='["https://prompt-to-3d-frontend.vercel.app","http://localhost:5173","http://127.0.0.1:5173"]'
   DATABASE_URL=<SUPABASE_POSTGRES_URL>
   SESSION_TTL_HOURS=72
MIN_PASSWORD_CHARS=12
AUTH_RATE_LIMIT_ATTEMPTS=5
   ADMIN_USER_IDS='["admin"]'
   R2_ACCOUNT_ID=<CLOUDFLARE_ACCOUNT_ID>
   R2_ACCESS_KEY_ID=<R2_ACCESS_KEY_ID>
   R2_SECRET_ACCESS_KEY=<R2_SECRET_ACCESS_KEY>
   R2_BUCKET_NAME=prompt-to-3d

   # Models are separate. Do not add/download them for API-only testing.
   SDXL_MODEL_PATH=/root/models/sdxl
   SDXL_LORA_PATH=
   SDXL_LORA_SCALE=1.0
   HUNYUAN_MODEL_PATH=/root/models/hunyuan3d-2.1
   HUNYUAN_FINETUNED_MODEL_PATH=
   HUNYUAN_SUBFOLDER=hunyuan3d-dit-v2-1
   HUNYUAN_REPO_PATH=/root/Hunyuan3D-2.1
   SDXL_TIMEOUT_SECONDS=900
   ```

6. Install the supervisor service:

   ```bash
   cat > /etc/supervisor/conf.d/prompt-to-3d-backend.conf <<'EOF'
   [program:prompt-to-3d-backend]
   directory=/root/Prompt-to-3d/PT3-backend
   command=/root/Prompt-to-3d/PT3-backend/venv/bin/python run.py
   autostart=true
   autorestart=true
   startsecs=5
   stopasgroup=true
   killasgroup=true
   stdout_logfile=/var/log/prompt-to-3d-backend.out.log
   stderr_logfile=/var/log/prompt-to-3d-backend.err.log
   environment=PYTHONUNBUFFERED="1"
   EOF

   supervisorctl reread
   supervisorctl update
   supervisorctl restart prompt-to-3d-backend || supervisorctl start prompt-to-3d-backend
   ```

7. Verify backend health:

   ```bash
   supervisorctl status prompt-to-3d-backend
   curl http://127.0.0.1:<CHEAPCUDA_HTTP_PORT>/health
   curl http://<GPU_IP>:<CHEAPCUDA_HTTP_PORT>/health
   ```

8. Update `PT3-frontend/vercel.json` so `/api/(.*)` points to the new public backend:

   ```json
   {
     "source": "/api/(.*)",
     "destination": "http://<GPU_IP>:<CHEAPCUDA_HTTP_PORT>/$1"
   }
   ```

9. Deploy frontend to Vercel:

   ```powershell
   cd PT3-frontend
   vercel --prod --yes
   ```

10. Final verification:

    ```powershell
    curl.exe https://prompt-to-3d-frontend.vercel.app/api/health
    ```

## Restart While Same GPU Is Still Alive

Use this if the backend process crashes but the CheapCUDA machine still exists:

```bash
ssh root@<GPU_IP> -p <SSH_PORT>
supervisorctl status prompt-to-3d-backend
supervisorctl restart prompt-to-3d-backend
tail -80 /var/log/prompt-to-3d-backend.err.log
curl http://127.0.0.1:<CHEAPCUDA_HTTP_PORT>/health
```

## Important

CheapCUDA machines are not permanent. When you delete the rented GPU, files on it
are gone. That is fine for this app as long as:

- Supabase keeps users/jobs/history.
- Cloudflare R2 keeps generated image/GLB files.
- The frontend rewrite is updated to the new GPU IP and port.
- Model weights are either downloaded again or restored from separate storage.
