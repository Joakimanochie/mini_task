from groq import Groq
import os
import gradio as gr
from dotenv import load_dotenv
from functions import image_encorder, analyse_image


with gr.Blocks(title='Image Grader') as app:

    gr.Markdown('# Image Comparison Grader')
    gr.Markdown('Upload the original image and the hand-drawn verson, then click **Analyse**')

    with gr.Row():
        original_input = gr.Image(label='Original Image', type='filepath', height=300)
        drawn_input = gr.Image(label='Drawn Image', type='filepath', height=300)

    analyse_btn = gr.Button('Analyse', variant='primary', size='lg')
    result_output = gr.Textbox(label= 'Analysis Result', lines=15, placeholder=' Results will appear here')

    analyse_btn.click(fn=analyse_image, inputs=[original_input, drawn_input], outputs=result_output)

app.launch(share=True)
