from openai import OpenAI
import streamlit as st
import chatmol_fn as cfn
from stmol import showmol
from streamlit_float import *
from viewer_utils import show_pdb, update_view
from utils import test_openai_api
from streamlit_molstar import st_molstar, st_molstar_rcsb, st_molstar_remote
import new_function_template
import shutil
from chat_helper import ConversationHandler, compose_chat_completion_message
import os
import json
from typing import Dict
import pickle
import re
import streamlit_analytics
import requests

st.set_page_config(layout="wide")
st.session_state.new_added_functions = []
try:
    print(st.session_state["messages"])
except:
    pass

pattern = r"<chatmol_sys>.*?</chatmol_sys>"
# wide
if "cfn" in st.session_state:
    cfn = st.session_state["cfn"]
else:
    cfn = cfn.ChatmolFN()
    st.session_state["cfn"] = cfn

st.title("ChatMol copilot", anchor="center")
st.sidebar.write("2023 Dec 16 public version")
st.sidebar.write(
    "ChatMol copilot is a copilot for protein engineering. Also chekcout our [GitHub](https://github.com/JinyuanSun/ChatMol)."
)
st.write("Enjoy modeling proteins with ChatMol copilot! 🤖️ 🧬")
float_init()

st.sidebar.title("Settings")
with streamlit_analytics.track():
    project_id = st.sidebar.text_input("Project Name", "Project-X")
openai_api_key = st.sidebar.text_input("OpenAI API key", type="password")

try:
    openai_api_key = os.getenv("OPENAI_API_KEY", openai_api_key)
except:
    print("No OPENAI_API_KEY found in environment variables")

if project_id + str(openai_api_key) == "Project-X":
    st.warning(
        "Please change the project name to your own project name, and provide your own OpenAI API key."
    )
    st.stop()

model = st.sidebar.selectbox(
    "Model",
    ["gpt-3.5-turbo-1106", "gpt-4-32k-0613", "gpt-3.5-turbo-16k", "gpt-4-1106-preview"],
)
st.session_state["openai_model"] = model


if "api_key" in st.session_state:
    api_key_test = st.session_state["api_key"]
    if st.session_state.api_key is False:
        api_key_test = test_openai_api(openai_api_key)
        st.session_state.api_key = api_key_test
        if api_key_test is False:
            st.warning(
                "The provided OpenAI API key seems to be invalid. Please check again. If you don't have an OpenAI API key, please visit https://platform.openai.com/ to get one."
            )
            st.stop()
else:
    api_key_test = test_openai_api(openai_api_key)
    st.session_state["api_key"] = api_key_test


hash_string = "WD_" + str(hash(openai_api_key + project_id)).replace("-", "_")
if st.sidebar.button("Clear Project History"):
    if os.path.exists(f"./{hash_string}"):
        shutil.rmtree(f"./{hash_string}")
        st.session_state.messages = []
# try to bring back the previous session
work_dir = f"./{hash_string}"
cfn.WORK_DIR = work_dir
if not os.path.exists(work_dir):
    os.makedirs(work_dir)
if os.path.exists(f"{work_dir}/.history"):
    with open(f"{work_dir}/.history", "rb") as f:
        st.session_state.messages = pickle.load(f)

client = OpenAI(api_key=openai_api_key)
conversation = ConversationHandler(client, cfn, model_name=model)

if add_translator := st.sidebar.checkbox("Add translator"):
    def translate_to_protein(self, seq:str, pname=None):
        from Bio.Seq import Seq
        nucleotide_seq = Seq(seq)
        protein_seq = nucleotide_seq.translate()
        if pname:
            return f"The protein sequence of {seq} is `>protein\n{protein_seq}`\n{pname}"
        else:
            return f"The protein sequence of {seq} is `>protein\n{protein_seq}`"

    cfn.translate_to_protein = translate_to_protein.__get__(cfn)

    conversation.tools.append(
        {
            "type": "function",
            "function": {
                "name": "translate_to_protein",
                "description": "Translate a DNA/RNA sequence to a protein sequence",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seq": {"type": "string", "description": "The DNA/RNA sequence"},
                    },
                },
                "required": ["seq"],
            },
        }
    )
    conversation.available_functions["translate_to_protein"] = cfn.translate_to_protein

if add_from_template := st.sidebar.checkbox("Add from template"):
    function_info = new_function_template.get_info()
    descriptions = function_info['descriptions']
    new_funcs = function_info['functions']
    test_data = new_function_template.test_data
    for description, new_func in zip(descriptions, new_funcs):
        try:
            test_results = new_function_template.test_new_function(new_func, description['function']['name'], test_data)
            conversation.tools.append(description)
            conversation.available_functions[description['function']['name']] = new_func.__get__(cfn)
            if description['function']['name'] not in st.session_state.new_added_functions:
                st.sidebar.success(f"Function `{description['function']['name']}` added successfully.")
                st.session_state.new_added_functions.append(description['function']['name'])
        except Exception as e:
            st.warning(f"Failed to add function from template. Error: {e}")

available_functions = conversation.available_functions
available_tools = conversation.tools
if "openai_model" not in st.session_state:
    st.session_state["openai_model"] = model

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "system",
            "content": "You are ChatMol copilot, a helpful copilot in molecule analysis with tools. Use tools only when you need them. Only answer to questions related molecular modelling.",
        }
    ]

chatcol, displaycol = st.columns([1, 1])
with chatcol:
    for message in st.session_state.messages:
        # print(type(message))
        try:
            if message["role"] != "system":
                cleaned_string = re.sub(
                    pattern, "", message["content"], flags=re.DOTALL
                )
                if cleaned_string != "":
                    with st.chat_message(message["role"]):
                        st.markdown(cleaned_string)
        except:
            if message.role != "system":
                cleaned_string = re.sub(pattern, "", message.content, flags=re.DOTALL)
                if cleaned_string != "":
                    with st.chat_message(message.role):
                        st.markdown(cleaned_string)

if prompt := st.chat_input("What is up?"):
    with chatcol:
        if os.path.exists(f"{work_dir}/.workspace"):
            chatmol_sys_info = open(f"{work_dir}/.workspace", "r").read()
            prompt += chatmol_sys_info
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            cleaned_string = re.sub(pattern, "", prompt, flags=re.DOTALL)
            st.markdown(cleaned_string)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            tool_calls = []
            tool_call = None
            for response in client.chat.completions.create(
                model=st.session_state["openai_model"],
                messages=st.session_state.messages,
                stream=True,
                tools=available_tools,
                tool_choice="auto",
            ):
                full_response += response.choices[0].delta.content or ""
                message_placeholder.markdown(full_response + "▌")
                tool_call_chunk_list = response.choices[0].delta.tool_calls
                if tool_call_chunk_list:
                    for tool_call_chunk in tool_call_chunk_list:
                        if len(tool_calls) <= tool_call_chunk.index:
                            tool_calls.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        tool_call = tool_calls[tool_call_chunk.index]
                        if tool_call_chunk.id:
                            tool_call["id"] += tool_call_chunk.id
                        if tool_call_chunk.function.name:
                            tool_call["function"][
                                "name"
                            ] += tool_call_chunk.function.name
                        if tool_call_chunk.function.arguments:
                            tool_call["function"][
                                "arguments"
                            ] += tool_call_chunk.function.arguments
            function_response = ""
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": full_response,
                }
            )
            if tool_call:
                response_message = compose_chat_completion_message(
                    role="assistant",
                    content=full_response,
                    tool_call_dict_list=tool_calls,
                )
                st.session_state.messages.append(response_message)
                for tool_call in tool_calls:
                    function_name = tool_call["function"]["name"]
                    function_to_call = available_functions[function_name]
                    try:
                        function_args = json.loads(tool_call["function"]["arguments"])
                        function_response = function_to_call(**function_args)
                        st.session_state.messages.append(
                            {
                                "tool_call_id": tool_call["id"],
                                "role": "tool",
                                "name": function_name,
                                "content": function_response,
                            }
                        )
                    except Exception as e:
                        print(f"The error is:\n{e}")
                        st.session_state.messages.append(
                            {
                                "tool_call_id": tool_call["id"],
                                "role": "tool",
                                "name": function_name,
                                "content": f"error: {e}",
                            }
                        )
            # if full_response:
            # message_placeholder.markdown(full_response)
            if function_response:
                for response in client.chat.completions.create(
                    model=st.session_state["openai_model"],
                    messages=st.session_state.messages,
                    stream=True,
                ):
                    full_response += response.choices[0].delta.content or ""
                    message_placeholder.markdown(full_response)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": full_response,
                    }
                )

            message_placeholder.markdown(full_response)
            # print(st.session_state.messages)
uploaded_file = st.sidebar.file_uploader("Upload PDB file", type=["pdb"])

if uploaded_file:
    chatmol_system_prompt = f" <chatmol_sys> File path information: The path to protein uploaded is {work_dir}/{uploaded_file.name}, the workdir is {work_dir} </chatmol_sys>"
    with open(f"{work_dir}/.workspace", "w+") as f:
        f.write(chatmol_system_prompt)
    pdb_id = uploaded_file.name.split(".")[0]
    pdb_file = f"{cfn.WORK_DIR}/{pdb_id}.pdb"
    with open(pdb_file, "wb") as f:
        f.write(uploaded_file.getbuffer())

    pdb_string = "\n".join(
        [
            x
            for x in uploaded_file.getvalue().decode("utf-8").split("\n")
            if x.startswith("ATOM") or x.startswith("HETATM")
        ]
    )
    view = show_pdb(
        pdb_str=pdb_string,
        color=color_options["Rainbow"],
        show_sidechains=False,
        show_ligands=True,
        show_mainchains=False,
    )

    cfn.VIEW_DICTS[pdb_id] = view


with displaycol:
    container = st.container()
    with container:
        col1, col2 = st.columns([1, 1])
        with col1:
            viewer_selection = st.selectbox(
                "Select a viewer", options=["molstar", "py3Dmol"], index=0
            )
        if viewer_selection == "molstar":
            pdb_files = [f for f in os.listdir(cfn.WORK_DIR) if f.endswith(".pdb")]
            if len(pdb_files) > 0:
                with col2:
                    pdb_file = st.selectbox(
                        "Select a pdb file", options=pdb_files, index=0
                    )
                st_molstar(f"{cfn.WORK_DIR}/{pdb_file}", height=500)
        if viewer_selection == "py3Dmol":
            color_options = {
                "Confidence": "pLDDT",
                "Rainbow": "rainbow",
                "Chain": "chain",
            }
            selected_color = st.sidebar.selectbox(
                "Color Scheme", options=list(color_options.keys()), index=0
            )
            # print(selected_color)
            show_sidechains = st.sidebar.checkbox("Show Sidechains", value=False)
            show_mainchains = st.sidebar.checkbox("Show Mainchains", value=False)
            show_ligands = st.sidebar.checkbox("Show Ligands", value=True)
            if len(cfn.VIEW_DICTS) > 0:
                with col2:
                    select_view = st.selectbox(
                        "Select a view", options=list(cfn.VIEW_DICTS.keys()), index=0
                    )
                view = cfn.VIEW_DICTS[select_view]
                showmol(view, height=400, width=500)
        float_parent()

with open(f"{work_dir}/.history", "wb") as f:
    pickle.dump(st.session_state.messages, f)
