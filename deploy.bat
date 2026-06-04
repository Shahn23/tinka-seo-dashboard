@echo off
setlocal
echo ====================================
echo  Tinka SEO Dashboard - Vercel Deploy
echo ====================================
echo.
echo Step 1: Install Vercel CLI (one time only)
call npm install -g vercel 2>nul
echo.
echo Step 2: Deploy to production
echo Copying fresh database...
copy /Y data\seo_dashboard.db api\seo_dashboard.db
echo Deploying...
:: Token removed for GitHub safety - use `vercel --prod --yes` with VERCEL_TOKEN env var
call vercel --prod --yes
echo.
if %ERRORLEVEL% EQU 0 (
    echo ====================================
    echo  Deploy successful!
    echo  Your dashboard is live at:
    echo  https://tinka-seo-dashboard.vercel.app
    echo ====================================
) else (
    echo Deployment failed. See errors above.
)
endlocal
pause
