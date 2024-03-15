import streamlit as st
import boto3
import pdfkit
# import tempfile
import os
import subprocess
import json
from datetime import datetime
import fitz  # PyMuPDF

if 'pdf_file_path' not in st.session_state:
    st.session_state.pdf_file_path = None

def download_file_from_s3_and_convert_to_pdf(company_number, bucket_name='company-house'):
    s3 = boto3.client('s3')
    s3_key = f"xhtml/{company_number}.xhtml"
    xhtml_file_path = f"/tmp/{company_number}.xhtml"
    s3.download_file(bucket_name, s3_key, xhtml_file_path)
    
    # Convert XHTML to PDF
    annotations_dir = "annotations"
    if not os.path.exists(annotations_dir):
        os.makedirs(annotations_dir)
    output_pdf_path = os.path.join(annotations_dir, f"{company_number}.pdf")
    pdfkit.from_file(xhtml_file_path, output_pdf_path)
    
    st.session_state.pdf_file_path = output_pdf_path
    
    return output_pdf_path

def extract_annotations(pdf_path):
    annotations = []
    with fitz.open(pdf_path) as pdf_doc:
        for page_number in range(len(pdf_doc)):
            page = pdf_doc.load_page(page_number)
            page_annotations = page.annots()
            if page_annotations:  # Check if there are any annotations on the page
                for annotation in page_annotations:
                    annotation_dict = {
                        'type': annotation.type[0],
                        'rect': [annotation.rect.x0, annotation.rect.y0, annotation.rect.x1, annotation.rect.y1],  # Convert Rect to list
                        'content': annotation.info.get('content', ''),
                    }
                    if annotation.type[0] == 8:  # Highlight
                        adjusted_rect = fitz.Rect(annotation.rect.x0, annotation.rect.y0, annotation.rect.x1, annotation.rect.y1 - 1)
                        highlighted_text = page.get_textbox(adjusted_rect)
                        annotation_dict['highlighted_text'] = highlighted_text
                    annotations.append(annotation_dict)
                    st.write(f'annotations from inside fn: {annotations}')
    return annotations

def upload_annotations_to_s3(company_number, pdf_path, bucket_name='company-house'):
    s3 = boto3.client('s3')
    annotations = extract_annotations(pdf_path)
    st.write(f'annotations: {annotations}')
    st.write(f'pdf path: {pdf_path}')
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    s3_key = f"annotations/{company_number}_{timestamp}.json"
    annotations_file_path = f"/tmp/{company_number}_{timestamp}.json"
    with open(annotations_file_path, 'w') as file:
        # Dump the JSON with an indentation of 4 spaces
        json.dump({'annotations': annotations}, file, indent=4)  # Wrap annotations list in a dictionary before dumping to JSON
    
    # Set the Content-Type metadata to application/json
    s3.upload_file(annotations_file_path, bucket_name, s3_key, ExtraArgs={'ContentType': 'application/json'})
    
    os.remove(annotations_file_path)  # Clean up local file
    return s3_key

st.title("ArgoXai")
st.subheader("XHTML annotation")

col1, col2, col3, c4, c5, c6, c7 ,c8 = st.columns([3,3,1,1,1,1,1,1])
company_number = col1.text_input("Enter the company number")

if col1.button("Retrieve XHTML and Convert to PDF"):
    st.session_state.pdf_file_path = download_file_from_s3_and_convert_to_pdf(company_number)
    if st.session_state.pdf_file_path:
        with open(st.session_state.pdf_file_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
            st.download_button(label="Download PDF",
                               data=pdf_bytes,
                               file_name=f"{company_number}.pdf",
                               mime="application/pdf")
        st.success("PDF successfully generated. Please download using the button above.")
    else:
        st.error("XHTML file not found for the given company number.")

if st.button("Upload Annotations"):
    upload_status = upload_annotations_to_s3(company_number, st.session_state.pdf_file_path)
    if upload_status:
        st.success("Annotations successfully uploaded to S3.")
    else:
        st.error("Failed to upload annotations.")
