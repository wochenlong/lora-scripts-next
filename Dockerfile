FROM nvcr.io/nvidia/pytorch:24.07-py3

EXPOSE 28000

ENV TZ=Asia/Shanghai
ENV MAX_JOBS=4
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    apt update && apt install python3-tk ninja-build -y && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir /app

WORKDIR /app
RUN git clone https://github.com/wochenlong/lora-scripts-next.git lora-scripts

WORKDIR /app/lora-scripts
RUN pip install xformers==0.0.27.post2 --no-deps && \
    pip install -r requirements.txt && \
    pip install flash-attn==2.7.4.post1 --no-build-isolation && \
    python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('Flash Attention 2 OK')"

WORKDIR /app/lora-scripts/scripts
RUN pip install -r requirements.txt

WORKDIR /app/lora-scripts

CMD ["python", "gui.py", "--listen"]
