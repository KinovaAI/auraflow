# ================================================
# AuraFlow Web Dockerfile — production only
# ================================================

FROM node:20-alpine AS base

WORKDIR /app

# ── Dependencies ─────────────────────────────────────────────────────────────
FROM base AS deps

COPY package.json package-lock.json* ./
RUN npm ci

# ── Production Builder ───────────────────────────────────────────────────────
FROM base AS builder

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

# Next.js bakes NEXT_PUBLIC_* vars into the bundle at build time
ARG NEXT_PUBLIC_API_URL=https://api.auraflow.fit
ARG NEXT_PUBLIC_APP_URL=https://app.auraflow.fit
ARG NEXT_PUBLIC_SQUARE_APPLICATION_ID=""
ARG NEXT_PUBLIC_SQUARE_LOCATION_ID=""
ARG NEXT_PUBLIC_SQUARE_ENVIRONMENT=production
ARG NEXT_PUBLIC_STRIPE_KEY=""
ARG NEXT_PUBLIC_GA_MEASUREMENT_ID=""
ARG NEXT_PUBLIC_FB_PIXEL_ID=""
ARG NEXT_PUBLIC_SENTRY_DSN=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL
ENV NEXT_PUBLIC_SQUARE_APPLICATION_ID=$NEXT_PUBLIC_SQUARE_APPLICATION_ID
ENV NEXT_PUBLIC_SQUARE_LOCATION_ID=$NEXT_PUBLIC_SQUARE_LOCATION_ID
ENV NEXT_PUBLIC_SQUARE_ENVIRONMENT=$NEXT_PUBLIC_SQUARE_ENVIRONMENT
ENV NEXT_PUBLIC_STRIPE_KEY=$NEXT_PUBLIC_STRIPE_KEY
ENV NEXT_PUBLIC_GA_MEASUREMENT_ID=$NEXT_PUBLIC_GA_MEASUREMENT_ID
ENV NEXT_PUBLIC_FB_PIXEL_ID=$NEXT_PUBLIC_FB_PIXEL_ID
ENV NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN

RUN mkdir -p public && npm run build

# ── Production Stage ─────────────────────────────────────────────────────────
FROM base AS production

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 auraflow && \
    adduser --system --uid 1001 auraflow

# sharp is required for Next.js Image optimization in standalone mode
RUN npm install --no-save sharp

WORKDIR /app

COPY --from=builder /app/public ./public
COPY --from=builder --chown=auraflow:auraflow /app/.next/standalone ./
COPY --from=builder --chown=auraflow:auraflow /app/.next/static ./.next/static

USER auraflow

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
