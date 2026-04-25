@echo off
cd /d "%~dp0"

wt ^
 --window 0 ^
  --size 100,14 ^
 new-tab --startingDirectory "%cd%"

