FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src/ ./src/
COPY scripts/ ./scripts/
ARG SCHEMA_CACHE_BUST=local
RUN echo "Schema cache bust: $SCHEMA_CACHE_BUST" && node scripts/fetch-schema.js
COPY index.js ./
ENV PORT=3000
EXPOSE 3000
CMD ["node", "index.js"]
