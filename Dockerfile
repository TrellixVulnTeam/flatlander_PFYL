# FROM continuumio/miniconda:latest
FROM tensorflow/tensorflow:2.1.0-py3

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

RUN apt-get update
RUN apt-get install -y wget rsync \
    xorg-dev \
    libglu1-mesa libgl1-mesa-dev \
    xvfb \
    libxinerama1 libxcursor1 \
    python-opengl \
    && rm -rf /var/lib/apt/lists/*

RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh

ENV PATH="/root/miniconda3/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=1

COPY ./environment-gpu.yml /src/environment.yml
RUN ls /src
RUN conda env create -f /src/environment.yml

ENV PATH /root/miniconda3/envs/flatland-rl/bin:$PATH
ENV CONDA_DEFAULT_ENV flatland-rl
ENV CONDA_PREFIX /root/miniconda3/envs/flatland-rl

SHELL ["/bin/bash", "-c"]

EXPOSE 8265

CMD conda --version && nvidia-smi
