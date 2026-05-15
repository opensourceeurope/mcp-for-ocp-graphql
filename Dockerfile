FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY index.js ./
COPY src/ ./src/
ENV PORT=3000
EXPOSE 3000
CMD ["node", "index.js"]
