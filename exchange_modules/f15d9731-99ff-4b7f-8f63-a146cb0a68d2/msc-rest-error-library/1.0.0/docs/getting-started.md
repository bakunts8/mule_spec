# Overview

This Library/API Fragment defines the Error response object as per the guidelines published by the MSC team. The scope behind it is to maximise consistency, but provide sufficient flexibility to enable adoption across the range of API led connectivity landscapes in which MSC operates.

It includes: 

 - Error dataType definition
 - Error response examples for most 4xx and 5xx status codes
 - Traits for base error responses and not found error response.

This library is targeting API designers creating API specifications in RAML 1.0. 

Refer to the Error Handling guidelines on Confluence for more information.

# How to consume the library

## Importing the library

This library is to be consumed by API specifications through Anypoint Design Center.  To do so, go to API specification page in Design Center and follow the steps below:

1 - Click on Exchange Dependencies
2 - Click on the '+' sign to add a new dependency
3 - Search for msc-rest-error-library
4 - Select the API fragment
5 - Choose the version you want to import
6 - Finally, click on Add 1 Dependency to import the fragment in the API specification.

You should now see a new folder in the API specification folder structure containing a copy of the MSC ERROR Library.

## Using the library

To apply the library to your API specification, use the `uses` function as seen below. This won't automatically apply the dataTypes and traits defined in the Library but will allow you to use them within your specification:

```
uses:
  errorLibrary: exchange_modules/<id>/msc-rest-error-library/1.0.0/msc-rest-error-library.raml
```

You can then refer to the Error dataType and traits from within your specification as follows:

```
types:
  error : errorLibrary.error

/status:
  is: [errorLibrary.baseErrorResponses]
  get:
    ...
```

# Upgrades

This library follows [SemVar](https://semver.org/) versioning approach, meaning that:

- When backwards-incompatible changes are made to the library, a new major version is released i.e. `x._._`
- When new features or enhancements are made to the library, a new minor version is released i.e. `_.y._`
- When bug-fixes are applies to the library, a new patch version is released i.e. `_._.z`

# Support

This library is actively maintained by the MSC team. 

For any assistance or support request, please contact the MSC team via email on _<>_.

# How to Contribute
_TBD_
