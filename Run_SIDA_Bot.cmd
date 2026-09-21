@echo off
chcp 65001 >nul
title SIDA Automation
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start_SIDA_Bot.ps1"
