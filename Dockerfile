# Use the official Python image from the Docker Hub
FROM python:3.10

# Install required packages
RUN apt-get update && apt-get install --yes \
    curl \
    openocd \
    ca-certificates curl \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    &&apt-get install --yes docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory for the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Install any dependencies specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Command to run your Python script along with the specified arguments
ENTRYPOINT ["python", "main.py"]
