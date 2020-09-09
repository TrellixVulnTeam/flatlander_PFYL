# FROM continuumio/miniconda:latest
FROM tensorflow/tensorflow:2.1.0-gpu-py3

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

ARG NB_USER
ARG NB_UID
ENV USER ${NB_USER}
ENV HOME /home/${NB_USER}

RUN adduser --disabled-password \
    --gecos "Default user" \
    --uid ${NB_UID} \
    --home ${HOME} \
    ${NB_USER}

USER root

RUN apt-get update
RUN apt-get install -y wget rsync git \
    xorg-dev \
    libglu1-mesa libgl1-mesa-dev \
    xvfb \
    libxinerama1 libxcursor1 \
    python-opengl \
    && rm -rf /var/lib/apt/lists/*

COPY environment-gpu.yml /src/environment-gpu.yml

RUN chown -R ${NB_UID}:${NB_UID} ${HOME}
RUN chown -R ${NB_UID}:${NB_UID} /src

WORKDIR ${HOME}
USER ${NB_USER}
RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir ${HOME}/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh

ENV PATH="/root/miniconda3/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=1

RUN ls /src
RUN conda env create -f /src/environment-gpu.yml

ENV PATH ${HOME}/miniconda3/envs/flatland-rl/bin:$PATH
ENV CONDA_DEFAULT_ENV flatland-rl
ENV CONDA_PREFIX ${HOME}/miniconda3/envs/flatland-rl

RUN python3 -m pip install git+https://gitlab.aicrowd.com/flatland/flatland.git

SHELL ["/bin/bash", "-c"]

CMD conda --version && nvidia-smi
