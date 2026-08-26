# Industrial Maintenance Copilot - Frontend Web Dockerfile
FROM node:22-alpine AS builder

WORKDIR /app
ARG API_BASE_URL=http://api:8000
ENV API_BASE_URL=${API_BASE_URL}

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source code
COPY . .

# Build application
RUN npm run build

# Production image
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Copy standalone output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
