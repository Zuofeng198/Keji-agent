@echo off
pushd "%~dp0"
node --experimental-strip-types src/index.ts
