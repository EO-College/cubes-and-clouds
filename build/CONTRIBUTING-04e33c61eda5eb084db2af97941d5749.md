# How to contribute
This is a online course about Open Science on EO Cloud Platforms. By it's nature, the topic is fast paced and keeping up with the development of cloud technologies, standards and concepts isn't easy. To keep up to date and to maintain a functioning exercises we would really appreciate your contributions!

## Types of contributions
We're happy to receive contributions to improve the quality of the course. Here are some potential areas where help would be greatly appreciated
### Review
- Read through the material through the [rendered web pages](http://eo-college.github.io/cubes-and-clouds). However, bear in mind that the official content of the course is available on the EO-College platform at [https://eo-college.org/courses/cubes-and-clouds/](https://eo-college.org/courses/cubes-and-clouds/) and you may find slightly differences between the two material. We strongly encourage you to check both content before suggesting changes. 
- If you want to **fix something directly**: Open a pull request to fix it. Don't add too much new information though. The lessons have a certain length.
- If you have **comments**: Open an issue for your review. Name it for example "Review Section 1.3 Open Science". Add all comments you have in that issue with links to the file where they apply.

### Other
- **Adding new content:** If you have an idea for new content, please open an issue to discuss this.
- **Report Bugs:** If any of the exercises are not working. Please report a bug here by opening an issue.
- **Fix Bugs:** Make a pull request with your fix.

### Generate Rendered Web Pages Locally

We recommend you render the web pages locally to check your changes. Below is a short guide on how to generate the rendered web pages locally:

1. If conda is installed on your platform, you can skip this first step. Otherwise, we recommend you install [miniconda](https://docs.anaconda.com/miniconda/install/).
2. Create the `cubes-and-clouds` conda environment (`environment.yml` file is located in the root folder of the **cubes-and-clouds** github repository: 
```
conda env create -f environment.yml
```
3. Build the rendered web pages using [Jupyter Book](https://jupyterbook.org):
```
jupyter-book build lectures
```
4. To visualize the rendered web pages, open `lectures/_build/html/index.html` in your preferred web browser from the root folder of the **cubes-and-clouds** GitHub repository.

## Acknowledgement 
We want every conrtibution to be acknwoledged. That's why we have the [all-contributors](https://allcontributors.org/) bot installed. It allows you to acknowledge your own contributions and to appear in the [CONTRIBUTORS.md](CONTRIBUTORS.md). If you want your contribution to be acknowledged **Comment on your Issue or Pull Request, asking the @all-contributors bot to add a contributor (likely yourself)**:
```
@all-contributors please add @<username> for <contributions>
```
- Here's the list of [possible contribution types](https://allcontributors.org/docs/en/emoji-key)
- For more detailed information check the [bot usage documentation](https://allcontributors.org/docs/en/bot/usage)
A real example would look like this
```
@all-contributors please add @przell for maintenance
```
