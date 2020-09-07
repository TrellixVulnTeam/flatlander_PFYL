# FROM continuumio/miniconda:latest
FROM tensorflow/tensorflow:2.1.0-gpu-py3

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

ARG NB_USER
ARG NB_UID
ENV USER ${NB_USER}
ENV HOME /root/${NB_USER}

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${NB_UID} \
    ${NB_USER}

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

COPY environment-gpu.yml /src/environment-gpu.yml
RUN ls /src
RUN conda env create -f /src/environment-gpu.yml

ENV PATH /root/miniconda3/envs/flatland-rl/bin:$PATH
ENV CONDA_DEFAULT_ENV flatland-rl
ENV CONDA_PREFIX /root/miniconda3/envs/flatland-rl

SHELL ["/bin/bash", "-c"]

USER ${NB_USER}

CMD conda --version && nvidia-smi
