# Build stage
FROM node:22-slim AS builder

WORKDIR /app

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_PMS_CHAT

ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
ENV VITE_PMS_CHAT=$VITE_PMS_CHAT

COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm install

COPY . .

# Remove any stale .env files left on the host — they're gitignored so
# `git pull` never cleans them up, and Vite reads them at build time
# regardless of the ARGs/ENV set above, silently overriding this build.
RUN rm -f .env .env.local .env.production .env.production.local .env.development .env.development.local

RUN npm run build

# Runtime stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]