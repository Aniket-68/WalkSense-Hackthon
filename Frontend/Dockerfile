# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json pnpm-lock.yaml* ./
RUN npm ci
COPY . .
RUN npm run build

# Serve stage — nginx serving static files
FROM nginx:1.27-alpine AS runner
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
