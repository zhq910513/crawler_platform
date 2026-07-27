FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker-entrypoint-wait.sh /usr/local/bin/docker-entrypoint-wait.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-wait.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint-wait.sh"]
CMD ["nginx", "-g", "daemon off;"]
