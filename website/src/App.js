import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import React, { useState, useEffect } from "react";
import axios from 'axios'
import awsExports from './aws-exports';
import { Amplify, Hub } from 'aws-amplify';

const components = {
  Header() {
    return <h1>Meeting Summarisation App</h1>;
  }
};

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileList, setFileList] = useState([]);
  const [summary, setSummary]  = useState([]);

  const listener = (data) => {
    switch (data?.payload?.event) {
      case 'signIn':
        loadFiles();
        break;
      case 'signOut':
        setSelectedFile(null);
        setFileList([]);
        setSummary("File Summary");
        break;
      default:
        break;
    }
  };
  
  Hub.listen('auth', listener);

  useEffect(() => {
    setSelectedFile(null);
    setFileList([]);
    setSummary("File Summary");
  }, []);

  async function handleSubmit(event) {
    event.preventDefault()

    const user = await Amplify.Auth.currentAuthenticatedUser();
    const token = user.signInUserSession.idToken.jwtToken;

    const auth_string = 'Bearer '.concat(token);

    const url = awsExports.API_GW;
    const url_generate_pre_signed = url+"/pre_signed_url?file="+selectedFile.name+"&name="+event.target.user.value
    axios.get(url_generate_pre_signed, { headers: { Authorization: auth_string } })
    .then(function (result) {
      var signedUrl = result.data.pre_signed_url;
      var options = {
        headers: {
          'Content-Type': selectedFile.type,
        }
      };
      return axios.put(signedUrl, selectedFile, options);
    })
    .then(function (result) {
      alert("File upload success - you will receive an email shortly");
      loadFiles()
    })
    .catch(function (err) {
      alert("File upload error!");
    });
  }
  function handleChange(event) {
    setSelectedFile(event.target.files[0])
  };

  async function loadFiles(file) {
    const user = await Amplify.Auth.currentAuthenticatedUser();
    const token = user.signInUserSession.idToken.jwtToken;

    const auth_string = 'Bearer '.concat(token);

    const url = awsExports.API_GW;
    const url_files = url+"/list_uploads";
    axios.get(url_files, { headers: { Authorization: auth_string } })
    .then(function (result) {
      var items = result.data;
      setFileList(items);
    })
    .catch(function (err) {
      alert("File load error!");
    });
  };

  async function downloadFile(file) {
    const user = await Amplify.Auth.currentAuthenticatedUser();
    const token = user.signInUserSession.idToken.jwtToken;
    const auth_string = 'Bearer '.concat(token);
    const url = awsExports.API_GW;
    const url_files = url+"/get_file?file="+file;

    axios.get(url_files, { headers: { Authorization: auth_string } })
    .then(function (result) {
      setSummary(result.data['combined_summary']['S']);
    })
    .catch(function (err) {
      alert("View File error!");
      setSummary("");
    });
  };

  return (
      <Authenticator
      components={components}
      >
          {({ signOut, user }) => (
              <div>
                <div className="top">
                  <button className="sign-out" onClick={signOut}>Sign out ({user.attributes.email})</button>
                  <h1>Transcribe & Translate Tool</h1>
                  <h2>Use this service to:</h2>
                  <ul>
                    <li>Transcribe an audio file (meeting) and provide full notes</li>
                    <li>Identify each speaker as part of the transcription</li>
                    <li>Translate the audio from <a href="https://docs.aws.amazon.com/translate/latest/dg/what-is-languages.html">supported languages</a> into English</li>
                    <li>Provide a short summary (1-2 lines) of the transcription</li>
                  </ul>
                  <form onSubmit={handleSubmit}>
                    <input type="file" onChange={handleChange}/>
                    <input type="hidden" name="user" value={user.username} />
                    <button type="submit">Submit</button>
                  </form>
                </div>
                <div className="bottom">
                  <h2>File uploads</h2>
                  <button type="submit" onClick={loadFiles}>Refresh files</button>
                  <ul>
                    {fileList.map(file => {
                      return (
                        <li key={file.file_name}>{file.file_original} | {
                          new Intl.DateTimeFormat('en-GB', { dateStyle: 'full', timeStyle: 'long' }).format((file.file_timestamp*1000))
                          } | <a href="#" onClick={() => downloadFile(file.file_name)} title="View Summary">View Summary</a></li>
                      )
                    })}
                  </ul>
                </div>
                <div className="summary" style={{whiteSpace: "pre-wrap"}}>{summary}</div>
              </div>
          )}
      </Authenticator>
  );
}

export default App;
