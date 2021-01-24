# link_finder

Obtain strings from JavaScript code that look like paths.

The strings are extracted by use of a _JavaScript parser_ ([Esprima](https://esprima.org/)) for better reliability than an approach solely relying on regular expressions.

Currently, the input can be either file paths or URLs to JavaScript files or HTML files. In the case of HTML files, the contents of `<scripts>` elements are extracted. Externally referenced script files can also be parsed by providing a flag.


## Usage

```
usage: link_finder.py [-h] [-i INPUT_FILE [INPUT_FILE ...]] [-u URL [URL ...]] [-c] [-j] [-e] [-t NUM_TOTAL_TIMEOUT_SECONDS] [-w] [-q]

Obtain strings from JavaScript code that look like paths.

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT_FILE [INPUT_FILE ...], --input-files INPUT_FILE [INPUT_FILE ...]
                        Paths to files storing JavaScript code or HTML documents to be scanned
  -u URL [URL ...], --urls URL [URL ...]
                        URLs of JavaScript code or HTML documents to be scanned.
  -c, --show-context    Output the context for each match rather than the match itself.
  -j, --json            Output the results in JSON.
  -e, --retrieve-external-scripts
                        Retrieve scripts referenced by the "src" attribute in input HTML documents.
  -t NUM_TOTAL_TIMEOUT_SECONDS, --timeout NUM_TOTAL_TIMEOUT_SECONDS
                        The total number of seconds to wait for an HTTP response for a resource.
  -w, --ignore-warnings
                        Do not output warning messages; only error messages and the results.
  -q, --quiet           Do not output warning messages or error messages.
```

### Example

#### Single JavaScript file, without context

```shell
$ ./link_finder.py -u 'https://online.auktionsverket.se/script/online180115_sv.js'
```

Output:
```
https://online.auktionsverket.se/script/online180115_sv.js
==========================================================
"/prg/sokutokad.asp?kat="
"/prg/sokrss.asp?kat="
"/prg/sprakinst.asp?sp="
"/prg/minneslistatabort.asp?anr="
"/prg/minsidatabortsok.asp?id="
"/prg/sokspara.asp?kat="
```

#### Single JavaScript file, with context

```shell
$ ./link_finder.py -u 'https://online.auktionsverket.se/script/online180115_sv.js' --show-context
```

Output:
```
https://online.auktionsverket.se/script/online180115_sv.js
==========================================================
window.location.assign("/prg/sokutokad.asp?kat="+document.formSok4.sokkategori.value+"&sok="+ escape(document.formSok2.sok.value)+"&typ="+document.formSok3.soktyp.value)
window.location.assign("/prg/sokrss.asp?kat="+document.formSok4.sokkategori.value+"&sok="+escape(document.formSok2.sok.value))
realobj.open("POST", "/prg/sprakinst.asp?sp="+sp,true)
realobj.open("POST", "/prg/minneslistatabort.asp?anr="+anr,true)
realobj.open("POST", "/prg/minsidatabortsok.asp?id="+id,true)
realobj.open("POST", "/prg/sokspara.asp?kat="+document.formSok4.sokkategori.value+"&sok="+escape(document.formSok2.sok.value),true)
```

(When output in a shell, the matches are highlighted.)

#### Single HTML file, with context, with external scripts (truncated)

```shell
$ ./link_finder.py -u 'https://online.auktionsverket.se' --show-context  --retrieve-external-scripts
```

Output:
```
https://online.auktionsverket.se script #1
==========================================
window.location.assign("/auktion/alla/")
realobj.open("POST", "/prg/sidinst.asp?antal="+document.form1.antalpersida.value+"&sort="+document.form1a.sortera.value+"&show="+document.form1c.showroom.value+"&ver=664816471",true)
realobj.open("POST", "/prg/sidinst.asp?antal="+document.form2.antalpersida.value+"&sort="+document.form2a.sortera.value+"&show="+document.form2c.showroom.value+"&ver=664816471",true)
realobj.open("POST", "/prg/cookie.asp",true)
window.location.assign("/auktion/alla/?sid="+document.form1b.sidval.value)
window.location.assign("/auktion/alla/?sid="+document.form2b.sidval2.value)

https://online.auktionsverket.se script #2
==========================================
$ss.find('.slideshow-wrap').append('<div class="slide"><a href="https://online.auktionsverket.se/auktion/sok/?u=0&sok=rantala&nysok=1" class="slide-link"><img alt="Stockholms Auktionsverk Magasin 5" src="https://online.auktionsverket.se/images/2021_01_Markku_sv.jpg"></a></div>')
$ss.find('.slideshow-wrap').append('<div class="slide"><a href="https://online.auktionsverket.se/auktion/sok/?u=0&sok=botaniska+b%F6cker&nysok=1" class="slide-link"><img alt="Stockholms Auktionsverk Magasin 5" src="https://online.auktionsverket.se/images/2021_01_botaniska_sv.jpg"></a></div>')
$ss.find('.slideshow-wrap').append('<div class="slide"><a href="http://auktionsverket.se/nyheter/salj-gratis-nar-du-bokar-fri-upphamtning/" class="slide-link"><img alt="Stockholms Auktionsverk Magasin 5" src="https://online.auktionsverket.se/images/2021_01_Kampanj.jpg"></a></div>')
$ss.find('.slideshow-wrap').append('<div class="slide"><a href="http://auktionsverket.se/nyheter/valkommen-till-verket-2/" class="slide-link"><img alt="Stockholms Auktionsverk Magasin 5" src="https://online.auktionsverket.se/images/20201115_Verket_SAV_CS-3.jpg"></a></div>')

https://online.auktionsverket.se/script/online180115_sv.js
==========================================================
window.location.assign("/prg/sokutokad.asp?kat="+document.formSok4.sokkategori.value+"&sok="+ escape(document.formSok2.sok.value)+"&typ="+document.formSok3.soktyp.value)
window.location.assign("/prg/sokrss.asp?kat="+document.formSok4.sokkategori.value+"&sok="+escape(document.formSok2.sok.value))
realobj.open("POST", "/prg/sprakinst.asp?sp="+sp,true)
realobj.open("POST", "/prg/minneslistatabort.asp?anr="+anr,true)
realobj.open("POST", "/prg/minsidatabortsok.asp?id="+id,true)
realobj.open("POST", "/prg/sokspara.asp?kat="+document.formSok4.sokkategori.value+"&sok="+escape(document.formSok2.sok.value),true)

...
```

:thumbsup: