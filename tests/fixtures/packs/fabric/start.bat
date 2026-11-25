@echo off
rem Minecraft 26.3 Fabric server (loader 0.20.1) - requires Java 25
cd /d "%~dp0"
title Minecraft Fabric Server 26.3

rem PATH java is 21, so point at the installed JDK 25 directly.
set "JAVA_EXE=C:\Program Files\Eclipse Adoptium\jdk-25.0.4.7-hotspot\bin\java.exe"
if not exist "%JAVA_EXE%" set "JAVA_EXE=java"

rem Memory: -Xms = initial heap, -Xmx = max heap (upper limit only, not preallocated).
rem No "nogui": the server GUI window opens, and this console window also accepts commands.
"%JAVA_EXE%" -Xms2G -Xmx16G -jar fabric-server-launch.jar

echo.
echo Server stopped.
pause
