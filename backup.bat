@echo off
cd /d E:\Project\Greetify\Greetify
if not exist backups mkdir backups
powershell -command "Copy-Item greetify.db ('backups\greetify_' + (Get-Date -Format yyyy-MM-dd) + '.db')"
echo Backup ho gaya: backups folder me dekho
pause