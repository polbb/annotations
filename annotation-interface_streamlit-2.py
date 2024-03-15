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

with open( "style.css" ) as css:
    st.markdown( f'<style>{css.read()}</style>' , unsafe_allow_html= True)

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
    annotator_name = None  # Initialize annotator_name as None
    with fitz.open(pdf_path) as pdf_doc:
        for page_number in range(len(pdf_doc)):
            page = pdf_doc.load_page(page_number)
            page_annotations = page.annots()
            if page_annotations:  # Check if there are any annotations on the page
                for annotation in page_annotations:
                    annotation_info = annotation.info
                    annotation_dict = {
                        'type': annotation.type[0],
                        'rect': [annotation.rect.x0, annotation.rect.y0, annotation.rect.x1, annotation.rect.y1],  # Convert Rect to list
                        'content': annotation_info.get('content', ''),
                        'info': annotation_info
                    }
                    if 'title' in annotation_info:  # Check if 'title' (annotator's name) exists
                        annotator_name = annotation_info['title']  # Assign annotator's name
                    if annotation.type[0] == 8:  # Highlight
                        adjusted_rect = fitz.Rect(annotation.rect.x0, annotation.rect.y0, annotation.rect.x1, annotation.rect.y1 - 1)
                        highlighted_text = page.get_textbox(adjusted_rect)
                        annotation_dict['highlighted_text'] = highlighted_text
                    annotations.append(annotation_dict)
    return annotations, annotator_name  # Return annotations and annotator_name

def upload_annotations_to_s3(company_number, pdf_path, bucket_name='company-house'):
    s3 = boto3.client('s3')
    annotations, annotator_name = extract_annotations(pdf_path)  # Extract annotations and annotator_name
    if not annotations:  # Check if there are no annotations
        st.error("No annotations found in the PDF.")
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    annotator_name = annotator_name.replace(" ", "_") if annotator_name else "Unknown_Annotator"  # Replace spaces with underscores or use "Unknown_Annotator"
    s3_key = f"annotations/{company_number}_{annotator_name}_{timestamp}.json"
    annotations_file_path = f"/tmp/{company_number}_{annotator_name}_{timestamp}.json"
    with open(annotations_file_path, 'w') as file:
        json.dump({'annotations': annotations}, file, indent=4)  # Wrap annotations list in a dictionary before dumping to JSON
    
    s3.upload_file(annotations_file_path, bucket_name, s3_key, ExtraArgs={'ContentType': 'application/json'})
    
    os.remove(annotations_file_path)  # Clean up local file
    st.success(f"Annotations successfully uploaded to S3 with key: {s3_key}")
    st.json({'annotations': annotations})  # Display annotations in JSON format on the screen
    return s3_key

st.title("ArgoXai")
st.subheader("Annotation tool")

st.divider()

col1, col2, col3, c4, c5, c6, c7 ,c8 = st.columns([5,3,1,1,1,1,1,1])
company_number = col1.text_input("Enter the company number")

if col1.button("Retrieve XHTML and Convert to PDF"):
    st.session_state.pdf_file_path = download_file_from_s3_and_convert_to_pdf(company_number)
    if st.session_state.pdf_file_path:
        annotations_dir = "annotations"
        if not os.path.exists(annotations_dir):
            os.makedirs(annotations_dir)
        pdf_file_full_path = os.path.join(annotations_dir, os.path.basename(st.session_state.pdf_file_path))
        try:
            with open(pdf_file_full_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
                st.download_button(label="Download PDF",
                                   data=pdf_bytes,
                                   file_name=f"{company_number}.pdf",
                                   mime="application/pdf")
            st.success("PDF successfully generated. Please download using the button above.")
        except FileNotFoundError:
            st.error("PDF file not found. Please ensure the file was generated correctly.")
    else:
        st.error("XHTML file not found for the given company number.")

st.divider()


uploaded_pdf = st.file_uploader("Choose a PDF file", type="pdf", key="pdf_uploader")
if uploaded_pdf is not None and st.button("Upload Annotations"):
    with open(uploaded_pdf.name, "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    st.session_state.pdf_file_path = uploaded_pdf.name
    upload_status = upload_annotations_to_s3(company_number, st.session_state.pdf_file_path)
    if upload_status:
        st.success("Annotations successfully uploaded to S3.")
    else:
        st.error("Failed to upload annotations.")
elif uploaded_pdf is None and st.button("Upload Annotations"):
    st.error("Please upload a PDF file.")
