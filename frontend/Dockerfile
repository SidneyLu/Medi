FROM node:20-alpine AS deps

WORKDIR /workspace/frontend
COPY frontend/package.json ./
RUN npm install

FROM node:20-alpine AS builder

WORKDIR /workspace/frontend
COPY --from=deps /workspace/frontend/node_modules ./node_modules
COPY frontend ./
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /workspace/frontend
ENV NODE_ENV=production
COPY --from=builder /workspace/frontend ./
EXPOSE 3000
CMD ["npm", "run", "start"]
