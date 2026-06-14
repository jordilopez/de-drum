# de-drum API Gateway — Node.js / Fastify
FROM node:24-slim

WORKDIR /app

# Copy package files and install deps
COPY package.json package-lock.json* ./
RUN npm install --omit=dev && npm cache clean --force

# Copy source
COPY src/ src/

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/api/health').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))" || exit 1

CMD ["node", "src/server.js"]
