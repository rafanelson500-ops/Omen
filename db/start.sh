docker run --name redis-local -p 6379:6379 -d redis
docker exec -it redis-local redis-cli