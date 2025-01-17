FROM tensorflow/tensorflow:2.3.0-gpu

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

COPY . ${HOME}

RUN chown -R ${NB_UID}:${NB_UID} ${HOME}

WORKDIR ${HOME}
USER ${NB_UID}
RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-py38_4.8.3-Linux-x86_64.sh \
    && mkdir ${HOME}/.conda \
    && bash Miniconda3-py38_4.8.3-Linux-x86_64.sh -b \
    && rm -f Miniconda3-py38_4.8.3-Linux-x86_64.sh

ENV PATH="${HOME}/miniconda3/bin:${PATH}"
ENV CUDA_VISIBLE_DEVICES=1

RUN conda update -n base -c defaults conda
RUN conda env create -f ${HOME}/environment.yml --verbose

ENV PATH ${HOME}/miniconda3/envs/flatland-rl/bin:$PATH
ENV CONDA_DEFAULT_ENV flatland-rl
ENV CONDA_PREFIX ${HOME}/miniconda3/envs/flatland-rl

RUN python3 -m pip install -r ${HOME}/requirements.txt

ENV AICROWD_TESTS_FOLDER ${HOME}/scratch/test-envs



SHELL ["/bin/bash", "-c"]

EXPOSE 8265

CMD conda --version && nvidia-smi
