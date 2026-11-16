#!/usr/bin/env bash
# Publica o projeto num Space do Hugging Face (SDK Docker).
#
# Uso:  ./scripts/publicar_hf.sh usuario/nome-do-space
#
# O que ele faz:
#   1. exporta o último commit do git (o .env e tudo que não foi commitado ficam de fora);
#   2. troca o README.md pelo deploy/huggingface/README.md, que tem o cabeçalho do Space;
#   3. envia o resultado para o Space, substituindo o conteúdo anterior.
#
# Na primeira vez o git pede usuário e senha: a senha é um token de acesso do
# Hugging Face com permissão de escrita (huggingface.co/settings/tokens).
set -euo pipefail

SPACE="${1:-}"
if [[ -z "$SPACE" || "$SPACE" != */* ]]; then
  echo "Uso: $0 usuario/nome-do-space" >&2
  exit 1
fi

RAIZ="$(git rev-parse --show-toplevel)"
cd "$RAIZ"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Aviso: há alterações não commitadas. Só o último commit vai para o Space." >&2
fi

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

git archive HEAD | tar -x -C "$TEMP"
cp deploy/huggingface/README.md "$TEMP/README.md"

COMMIT="$(git rev-parse --short HEAD)"
cd "$TEMP"
git init -q -b main
git add -A
git commit -q -m "Publica a versão $COMMIT do GitHub"
git push --force "https://huggingface.co/spaces/$SPACE" main

echo
echo "Enviado. Acompanhe o build em https://huggingface.co/spaces/$SPACE"
