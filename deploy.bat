@echo off
setlocal
echo ====================================
echo  Tinka SEO Dashboard - Vercel Deploy (v0.8)
echo ====================================
echo.
echo Step 1: Check Vercel CLI
where vercel >nul 2>nul || call npm install -g vercel
echo.
echo Step 2: Copy fresh database
copy /Y data\seo_dashboard.db api\seo_dashboard.db
echo.
echo Step 3: Deploy to production
echo.
echo To deploy, you need a Vercel token. Generate one at:
echo   https://vercel.com/account/tokens
echo.
echo Then run:   vercel --prod --yes --token YOUR_TOKEN
echo.
echo Or set env var:   set VERCEL_TOKEN=YOUR_TOKEN ^&^& vercel --prod --yes
echo.
echo ====================================
echo  Deployment instructions:
echo  1. Open https://vercel.com/account/tokens
echo  2. Create a new token (name: "tinka-dashboard-deploy")
echo  3. Run: vercel --prod --yes --token PASTE_TOKEN_HERE
echo  4. Your dashboard: https://tinka-seo-dashboard.vercel.app
echo ====================================
echo.
pause
