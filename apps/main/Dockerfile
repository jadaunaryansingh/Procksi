FROM node:22-slim

WORKDIR /app

# Copy dependency files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Expose port
EXPOSE 3002

# Run vite with host parameter to bind to 0.0.0.0
CMD ["npm", "run", "dev", "--", "--host"]
